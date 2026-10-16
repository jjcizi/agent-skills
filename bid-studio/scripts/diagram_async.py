#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bid-studio 异步绘图任务管理（diagram_async.py）

背景
----
logic-diagram 的 build.py 依赖 LibreOffice 渲染 PPTX→PDF→PNG，单幅常需
5~10 分钟。若在撰写标书时同步等待，会阻塞正文撰写主流程，甚至被跳过，
导致图片缺失或只生成一半。本脚本把「渲染」拆到后台进程执行，主流程不等待，
渲染完成后自动把图片回填到正文里的占位锚点位置。

机制
----
1. 撰写正文时，在需要配图的位置写占位锚点：`<!-- DIAGRAM:<id> -->`；
2. `add` 登记绘图任务（记录页号 / 映射文件 / 目标正文 / 图片路径）；
3. `run` / `run-all` 用后台进程启动渲染 worker，立即返回，主流程继续写；
4. worker 渲染完成后自动把锚点替换为图片引用 `![图题](图片路径)`；
5. 全部正文写完后 `sync` 汇合，确认所有图已完成并插入，未完成则报告。

任务单默认：工作区根 `中间件/绘图任务单.json`（可用 --tasks 覆盖）。
worker 日志：工作区根 `中间件/绘图日志/<id>.log`。

用法
----
  python3 scripts/diagram_async.py add --id D-001 --title 系统架构图 \
      --fig "图3-1 系统架构图" --page 43 --map 中间件/maps/map-D001.json \
      --outdir 技术文件/images --name 系统架构图 \
      --md 技术文件/03-第2章第1节-系统架构设计.md
  python3 scripts/diagram_async.py run D-001          # 后台渲染，立即返回
  python3 scripts/diagram_async.py run-all            # 后台启动全部 queued 任务
  python3 scripts/diagram_async.py status             # 查看任务状态
  python3 scripts/diagram_async.py sync               # 汇合：等待全部完成
  python3 scripts/diagram_async.py insert D-001       # 手动回填（兜底）
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
# vendor/logic-diagram 相对本脚本：scripts/../vendor/logic-diagram
LOGIC_DIR = os.path.normpath(os.path.join(HERE, '..', 'vendor', 'logic-diagram'))
LOGIC_BUILD = os.path.join(LOGIC_DIR, 'scripts', 'build.py')

DEFAULT_TASKS = os.path.join('中间件', '绘图任务单.json')
DEFAULT_LOG_DIR = os.path.join('中间件', '绘图日志')

STATUS_QUEUED = 'queued'
STATUS_RUNNING = 'running'
STATUS_DONE = 'done'
STATUS_FAILED = 'failed'


# --------------------------------------------------------------------------
# 任务单读写（原子写 + 简单锁，容忍 worker 与主流程并发访问）
# --------------------------------------------------------------------------
def _lock_path(tasks_file):
    return tasks_file + '.lock'


def _acquire_lock(lock_file, timeout=10.0):
    """简单排它锁：创建 lock 文件成功即持锁，否则退避重试。"""
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            if time.time() > deadline:
                return False
            time.sleep(0.2)


def _release_lock(lock_file):
    try:
        os.remove(lock_file)
    except OSError:
        pass


def load_tasks(tasks_file):
    if not os.path.exists(tasks_file):
        return {'tasks': []}
    try:
        with open(tasks_file, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {'tasks': []}


def save_tasks(tasks_file, data):
    os.makedirs(os.path.dirname(os.path.abspath(tasks_file)) or '.', exist_ok=True)
    lock = _lock_path(tasks_file)
    if not _acquire_lock(lock):
        raise RuntimeError(f'无法获取任务单锁：{lock}')
    try:
        tmp = tasks_file + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, tasks_file)
    finally:
        _release_lock(lock)


def find_task(data, task_id):
    for t in data['tasks']:
        if t['id'] == task_id:
            return t
    return None


def update_status(tasks_file, task_id, status, extra=None):
    """worker 完成后更新任务单状态（原子写）。"""
    data = load_tasks(tasks_file)
    t = find_task(data, task_id)
    if t is None:
        return False
    t['status'] = status
    if extra:
        t.update(extra)
    save_tasks(tasks_file, data)
    return True


# --------------------------------------------------------------------------
# 占位锚点与回填
# --------------------------------------------------------------------------
def anchor_of(task_id):
    return f'<!-- DIAGRAM:{task_id} -->'


def write_log(log_dir, task_id, text):
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f'{task_id}.log'), 'a', encoding='utf-8') as f:
        f.write(text + '\n')


def fill_anchor(md_path, anchor, img_md, fig):
    """把正文里的占位锚点替换为图片引用。返回是否替换成功。"""
    p = Path(md_path)
    if not p.exists():
        return False
    text = p.read_text(encoding='utf-8')
    if anchor not in text:
        return False
    replacement = f'![{fig}]({img_md})'
    p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
    return True


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------
def cmd_add(args):
    tasks_file = args.tasks
    data = load_tasks(tasks_file)
    if find_task(data, args.id):
        print(f'✗ 任务 {args.id} 已存在，请勿重复登记')
        return 1
    task = {
        'id': args.id,
        'title': args.title,
        'fig': args.fig,
        'kind': args.kind,           # logic | data
        'page': args.page,           # logic 页号（data 类可为 null）
        'map_file': args.map,        # 映射 JSON（logic 必填）
        'out_dir': args.outdir,
        'name': args.name,
        'target_md': args.md,
        'anchor': anchor_of(args.id),
        'status': STATUS_QUEUED,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'finished_at': None,
        'error': None,
    }
    data['tasks'].append(task)
    save_tasks(tasks_file, data)
    # 校验正文里已有锚点，没有则提示（不强制写，避免覆盖 agent 正在写的内容）
    md = Path(args.md)
    has_anchor = md.exists() and anchor_of(args.id) in md.read_text(encoding='utf-8')
    print(f'✓ 已登记任务 {args.id}：「{args.title}」')
    if not has_anchor:
        print(f'⚠ 正文 {args.md} 尚未找到占位锚点 {anchor_of(args.id)}，'
              f'请在配图位置补写该行，否则回填会失败')
    return 0


def cmd_run(args):
    tasks_file = args.tasks
    data = load_tasks(tasks_file)
    t = find_task(data, args.task_id)
    if t is None:
        print(f'✗ 任务 {args.id} 不存在')
        return 1
    if t['status'] == STATUS_RUNNING:
        print(f'⚠ 任务 {args.id} 已在渲染中，跳过')
        return 0
    return _spawn_worker(tasks_file, t, log_dir=args.log_dir)


def cmd_run_all(args):
    tasks_file = args.tasks
    data = load_tasks(tasks_file)
    queued = [t for t in data['tasks'] if t['status'] in (STATUS_QUEUED, STATUS_FAILED)]
    if not queued:
        print('✓ 没有待渲染的任务')
        return 0
    started = 0
    for t in queued:
        if _spawn_worker(tasks_file, t, log_dir=args.log_dir) == 0:
            started += 1
    print(f'✓ 已后台启动 {started} 个渲染任务（共 {len(queued)} 个排队）')
    print('  主流程可继续写正文；完成后自动回填，稍后跑 sync 汇合确认。')
    return 0


def _spawn_worker(tasks_file, task, log_dir):
    """启动后台 worker 进程渲染单个任务，立即返回。"""
    os.makedirs(os.path.dirname(tasks_file) or '.', exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    cmd = [sys.executable, os.path.abspath(__file__),
           '--tasks', os.path.abspath(tasks_file),
           '--log-dir', os.path.abspath(log_dir),
           '_worker', task['id']]
    try:
        if os.name == 'nt':
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP
                     | subprocess.DETACHED_PROCESS
                     | subprocess.CREATE_NO_WINDOW)
            subprocess.Popen(cmd, creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, close_fds=True)
        else:
            subprocess.Popen(cmd, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, close_fds=True)
        return 0
    except OSError as e:
        print(f'✗ 启动 worker 失败：{e}')
        return 1


def cmd_status(args):
    data = load_tasks(args.tasks)
    tasks = data['tasks']
    if not tasks:
        print('（暂无绘图任务）')
        return 0
    print(f"{'ID':<8} {'状态':<8} {'标题':<24} {'图题'}")
    print('-' * 78)
    for t in tasks:
        print(f"{t['id']:<8} {t['status']:<8} {t['title']:<24} {t['fig']}")
    n = {s: sum(1 for t in tasks if t['status'] == s)
         for s in (STATUS_QUEUED, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED)}
    print('-' * 78)
    print(f"queued {n[STATUS_QUEUED]} / running {n[STATUS_RUNNING]} / "
          f"done {n[STATUS_DONE]} / failed {n[STATUS_FAILED]}")
    return 0


def cmd_sync(args):
    tasks_file = args.tasks
    timeout = args.timeout
    interval = args.interval
    deadline = time.time() + timeout
    data = load_tasks(tasks_file)
    tasks = data['tasks']
    if not tasks:
        print('✓ 无绘图任务')
        return 0

    print('等待后台绘图完成…')
    while time.time() < deadline:
        data = load_tasks(tasks_file)
        pending = [t for t in data['tasks']
                   if t['status'] in (STATUS_QUEUED, STATUS_RUNNING)]
        if not pending:
            break
        running = [t for t in pending if t['status'] == STATUS_RUNNING]
        print(f'  进行中 {len(pending)}（渲染中 {len(running)}），'
              f'{interval}s 后再查…')
        time.sleep(interval)
    else:
        print(f'⚠ 超过 {timeout}s 仍有任务未完成，请稍后再 sync 或查看日志')

    data = load_tasks(tasks_file)
    failed = [t for t in data['tasks'] if t['status'] == STATUS_FAILED]
    done = [t for t in data['tasks'] if t['status'] == STATUS_DONE]
    pending = [t for t in data['tasks'] if t['status'] in (STATUS_QUEUED, STATUS_RUNNING)]

    print(f'\n✓ 完成 {len(done)} / 失败 {len(failed)} / 未完成 {len(pending)}')
    for t in failed:
        print(f'  ✗ {t["id"]} 「{t["title"]}」：{t.get("error") or "见日志"}')
    for t in pending:
        print(f'  ⏳ {t["id"]} 「{t["title"]}」仍在 {t["status"]}')
    return 0 if (not failed and not pending) else 1


def cmd_insert(args):
    """手动回填：把已完成任务的图片插回正文锚点（兜底）。"""
    data = load_tasks(args.tasks)
    t = find_task(data, args.task_id)
    if t is None:
        print(f'✗ 任务 {args.id} 不存在')
        return 1
    img_md = _img_md_path(t)
    # 图片是否已生成
    img_abs = os.path.join(t['out_dir'], t['name'] + '.png') \
        if t['kind'] == 'logic' else os.path.join(t['out_dir'], t['name'] + '.svg')
    if not os.path.exists(img_abs):
        print(f'✗ 图片尚未生成：{img_abs}')
        return 1
    if fill_anchor(t['target_md'], t['anchor'], img_md, t['fig']):
        print(f'✓ 已回填 {t["id"]} → {t["target_md"]}')
        update_status(args.tasks, args.id, STATUS_DONE)
        return 0
    print(f'✗ 未找到锚点 {t["anchor"]}，无法回填（正文可能已改动）')
    return 1


def _img_md_path(task):
    """图片相对 target_md 所在目录的 markdown 相对路径。"""
    if task['kind'] == 'logic':
        fname = task['name'] + '.png'
    else:
        fname = task['name'] + '.svg'
    img_abs = os.path.abspath(os.path.join(task['out_dir'], fname))
    md_dir = os.path.dirname(os.path.abspath(task['target_md']))
    return os.path.relpath(img_abs, md_dir).replace(os.sep, '/')


# --------------------------------------------------------------------------
# 后台 worker：渲染 + 自动回填（耗时点都在这里，但已脱离主流程）
# --------------------------------------------------------------------------
def worker_main(task_id, tasks_file, log_dir):
    write_log(log_dir, task_id,
              f'[{time.strftime("%H:%M:%S")}] worker 启动')
    update_status(tasks_file, task_id, STATUS_RUNNING)
    data = load_tasks(tasks_file)
    t = find_task(data, task_id)
    if t is None:
        return 1

    try:
        if t['kind'] == 'logic':
            if not os.path.exists(LOGIC_BUILD):
                raise RuntimeError(f'logic-diagram build.py 不存在：{LOGIC_BUILD}')
            cmd = [sys.executable, LOGIC_BUILD,
                   '--page', str(t['page']),
                   '--map', t['map_file'],
                   '--outdir', t['out_dir'],
                   '--name', t['name']]
        else:
            # data 类（kami SVG）通常秒级完成，这里同步渲染并回填即可。
            # 占位：实际 SVG 生成逻辑由 P6.9 决策树决定，未实现时明确报错。
            raise RuntimeError('data 类任务暂不支持后台渲染，请按 kami SVG 规则同步生成')

        write_log(log_dir, task_id, f'[{time.strftime("%H:%M:%S")}] 执行：' + ' '.join(cmd))
        proc = subprocess.run(cmd, cwd=os.getcwd(), capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
        if proc.returncode != 0:
            raise RuntimeError(f'build.py 退出码 {proc.returncode}：'
                               f'{(proc.stderr or proc.stdout or "")[-1500:]}')

        # 渲染成功 → 回填正文
        img_md = _img_md_path(t)
        if fill_anchor(t['target_md'], t['anchor'], img_md, t['fig']):
            write_log(log_dir, task_id, f'[{time.strftime("%H:%M:%S")}] 已回填 {img_md}')
            update_status(tasks_file, task_id, STATUS_DONE,
                          {'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'error': None})
            return 0
        else:
            raise RuntimeError(f'渲染完成但未找到锚点 {t["anchor"]}，'
                               f'请用 insert 手动回填')
    except Exception as e:  # noqa: BLE001
        write_log(log_dir, task_id, f'[{time.strftime("%H:%M:%S")}] 失败：{e}')
        update_status(tasks_file, task_id, STATUS_FAILED,
                      {'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'error': str(e)})
        return 1


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='bid-studio 异步绘图任务管理')
    ap.add_argument('--tasks', default=DEFAULT_TASKS, help='任务单 JSON 路径')
    ap.add_argument('--log-dir', default=DEFAULT_LOG_DIR, help='worker 日志目录')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_add = sub.add_parser('add', help='登记绘图任务')
    p_add.add_argument('--id', required=True)
    p_add.add_argument('--title', required=True)
    p_add.add_argument('--fig', required=True, help='图题，如「图3-1 系统架构图」')
    p_add.add_argument('--kind', default='logic', choices=('logic', 'data'))
    p_add.add_argument('--page', type=int, help='logic 页号')
    p_add.add_argument('--map', help='映射 JSON 路径（logic 必填）')
    p_add.add_argument('--outdir', required=True, help='图片输出目录')
    p_add.add_argument('--name', required=True, help='输出文件名（不含扩展名）')
    p_add.add_argument('--md', required=True, help='目标正文 md 路径')

    p_run = sub.add_parser('run', help='后台渲染单个任务')
    p_run.add_argument('task_id')

    sub.add_parser('run-all', help='后台启动全部 queued 任务')

    sub.add_parser('status', help='查看任务状态')

    p_sync = sub.add_parser('sync', help='等待全部任务完成')
    p_sync.add_argument('--timeout', type=int, default=1800, help='超时秒数（默认 1800）')
    p_sync.add_argument('--interval', type=int, default=30, help='轮询间隔秒（默认 30）')

    p_insert = sub.add_parser('insert', help='手动回填（兜底）')
    p_insert.add_argument('task_id')

    # worker 内部子命令（不对外文档化）
    p_worker = sub.add_parser('_worker', help=argparse.SUPPRESS)
    p_worker.add_argument('task_id')

    args = ap.parse_args()

    if args.cmd == '_worker':
        sys.exit(worker_main(args.task_id, args.tasks, args.log_dir))
    if args.cmd == 'add':
        sys.exit(cmd_add(args))
    if args.cmd == 'run':
        sys.exit(cmd_run(args))
    if args.cmd == 'run-all':
        sys.exit(cmd_run_all(args))
    if args.cmd == 'status':
        sys.exit(cmd_status(args))
    if args.cmd == 'sync':
        sys.exit(cmd_sync(args))
    if args.cmd == 'insert':
        sys.exit(cmd_insert(args))
    ap.print_help()
    sys.exit(2)


if __name__ == '__main__':
    main()
