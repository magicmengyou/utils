# 这是一个示例 Python 脚本。
import itertools as its
import datetime
import threading
import queue
import os
import mmap
import contextlib
from multiprocessing import cpu_count

# 配置参数
CHUNK_SIZE = 1000000  # 每批处理的密码数量
WORK_QUEUE_MAX_SIZE = 50  # 工作队列最大长度
RESULT_QUEUE_MAX_SIZE = 50  # 结果队列最大长度
UPDATE_INTERVAL = 1  # 进度更新间隔(秒)
USE_MEMORY_MAPPING = True  # 是否使用内存映射文件

# 记录程序运行时间
start = datetime.datetime.now()
words = '0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM'
r = 8  # 密码长度
exit_event = threading.Event()

# 创建工作队列和结果队列
work_queue = queue.Queue(maxsize=WORK_QUEUE_MAX_SIZE)
result_queue = queue.Queue(maxsize=RESULT_QUEUE_MAX_SIZE)

# 统计信息
total_combinations = len(words) ** r
processed_count = 0
last_updated = start
password_file = "alphabetPass.txt"

# 预计算字符映射表，加速组合生成
char_list = list(words)
char_count = len(char_list)


# 生成密码组合并放入工作队列
def generate_combinations():
    global processed_count
    batch = []
    count = 0

    # 使用迭代器分批生成组合
    for combo in its.product(words, repeat=r):
        if exit_event.is_set():
            break

        batch.append(combo)
        count += 1

        if len(batch) >= CHUNK_SIZE or count == total_combinations:
            work_queue.put(batch.copy())
            batch.clear()

    # 标记工作完成
    work_queue.put(None)
    print(f"\n总共有{count:,}种组合")


# 处理密码组合并放入结果队列
def process_combinations(worker_id):
    while not exit_event.is_set():
        try:
            batch = work_queue.get(timeout=1)
        except queue.Empty:
            continue

        if batch is None:  # 结束标志
            work_queue.put(None)
            break

        try:
            # 使用字节串拼接替代字符串操作，提升性能
            password_bytes = []
            for combo in batch:
                password_bytes.append(''.join(combo).encode('ascii') + b'\n')

            result_queue.put(password_bytes)
            print(f"Worker {worker_id} 处理了 {len(batch):,} 个组合")
        except Exception as e:
            print(f"Worker {worker_id} 错误: {e}")
            exit_event.set()
        finally:
            work_queue.task_done()


# 从结果队列读取并写入文件
def write_to_file():
    global processed_count, last_updated

    if USE_MEMORY_MAPPING:
        # 估计文件大小并预先分配空间
        estimated_size = total_combinations * (r + 1)  # 每个密码r字节+换行符
        with open(password_file, 'wb') as f:
            f.truncate(estimated_size)

        with open(password_file, 'r+b') as f:
            # 使用内存映射文件提升写入性能
            with contextlib.closing(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)) as mm:
                position = 0
                while not exit_event.is_set():
                    try:
                        passwords = result_queue.get(timeout=1)
                    except queue.Empty:
                        continue

                    if passwords is None:  # 结束标志
                        break

                    try:
                        # 批量写入内存映射文件
                        for pwd in passwords:
                            mm[position:position + len(pwd)] = pwd
                            position += len(pwd)

                        processed_count += len(passwords)

                        # 更新进度显示
                        current_time = datetime.datetime.now()
                        if (current_time - last_updated).total_seconds() >= UPDATE_INTERVAL:
                            show_progress()
                            last_updated = current_time
                    except Exception as e:
                        print(f"写入错误: {e}")
                        exit_event.set()
                    finally:
                        result_queue.task_done()
    else:
        # 传统文件写入方式
        with open(password_file, 'wb') as f:
            while not exit_event.is_set():
                try:
                    passwords = result_queue.get(timeout=1)
                except queue.Empty:
                    continue

                if passwords is None:  # 结束标志
                    break

                try:
                    # 批量写入字节数据
                    for pwd in passwords:
                        f.write(pwd)

                    processed_count += len(passwords)

                    # 更新进度显示
                    current_time = datetime.datetime.now()
                    if (current_time - last_updated).total_seconds() >= UPDATE_INTERVAL:
                        show_progress()
                        last_updated = current_time
                except Exception as e:
                    print(f"写入错误: {e}")
                    exit_event.set()
                finally:
                    result_queue.task_done()

    # 确保显示最终进度
    show_progress(True)
    # 标记写入完成
    result_queue.put(None)


# 显示进度条和估计剩余时间
def show_progress(final=False):
    if total_combinations <= 0:
        return

    progress = min(100.0, processed_count / total_combinations * 100)
    elapsed = (datetime.datetime.now() - start).total_seconds()

    # 计算剩余时间
    if processed_count > 0 and progress < 100:
        remaining_seconds = elapsed * (total_combinations - processed_count) / processed_count
        eta = format_time(remaining_seconds)
    else:
        eta = "计算中..."

    # 格式化已用时间
    elapsed_time = format_time(elapsed)

    # 计算速度
    if elapsed > 0:
        speed = processed_count / elapsed
        speed_str = f"{speed:,.1f} 密码/秒"
    else:
        speed_str = "计算中..."

    # 进度条长度
    bar_length = 50
    filled_length = int(bar_length * progress / 100)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)

    # 显示进度信息
    sys.stdout.write(f'\r进度: [{bar}] {progress:.2f}%  已用: {elapsed_time}  预计剩余: {eta}  速度: {speed_str}')
    if final:
        sys.stdout.write('\n')
    sys.stdout.flush()


# 格式化时间显示
def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:.0f}分{secs:.1f}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:.0f}时{minutes:.0f}分{secs:.1f}秒"


# 主执行流程
if __name__ == "__main__":
    # 获取CPU核心数，确定线程数量
    thread_count = min(8, max(2, cpu_count() - 1))  # 最多8个工作线程

    print(f"总密码组合数: {total_combinations:,}")
    print(f"使用 {thread_count} 个工作线程")
    print(f"使用内存映射: {'是' if USE_MEMORY_MAPPING else '否'}")
    print("开始生成密码本...")

    # 创建并启动线程
    threads = []

    # 生成器线程
    generator = threading.Thread(target=generate_combinations)
    generator.daemon = True
    generator.start()
    threads.append(generator)

    # 工作线程
    for i in range(thread_count):
        worker = threading.Thread(target=process_combinations, args=(i,))
        worker.daemon = True
        worker.start()
        threads.append(worker)

    # 写入器线程
    writer = threading.Thread(target=write_to_file)
    writer.daemon = True
    writer.start()
    threads.append(writer)

    # 等待所有线程完成或检测到退出信号
    try:
        for t in threads:
            while t.is_alive():
                t.join(timeout=1)
                if exit_event.is_set():
                    break
    except KeyboardInterrupt:
        print("\n用户中断，正在清理...")
        exit_event.set()

    # 确保队列处理完毕
    work_queue.join()
    result_queue.join()

    # 优化文件系统写入缓存
    if os.name == 'nt':  # Windows
        os.system(f"fsutil file seteof {password_file} {processed_count * (r + 1)}")
    elif os.name == 'posix':  # Linux/Mac
        with open(password_file, 'ab') as f:
            f.truncate(processed_count * (r + 1))

    end = datetime.datetime.now()
    print("生成密码本一共用了多长时间：{}".format(end - start))
    print(f'密码本已生成，大小: {os.path.getsize(password_file) / (1024 ** 3):.2f} GB')