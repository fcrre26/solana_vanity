import subprocess
import sys
import pkg_resources # type: ignore

def check_and_install_dependencies():
    """
    检查并安装所需的依赖库
    """
    required_packages = {
        'solders': 'solders',  # 改用 solders 包
        'base58': 'base58',
        'mnemonic': 'mnemonic'  # 添加助记词包
    }
    
    def install_package(package_name):
        print(f"正在安装 {package_name}...")
        try:
            # 安装新包
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"{package_name} 安装成功！")
            return True
        except subprocess.CalledProcessError:
            print(f"{package_name} 安装失败！")
            return False

    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    
    all_installed = True
    for package, pip_name in required_packages.items():
        if package.replace('-', '_') not in installed_packages:
            print(f"缺少依赖库: {package}")
            if not install_package(pip_name):
                all_installed = False
    
    if not all_installed:
        print("\n某些依赖库安装失败，程序可能无法正常运行。")
        input("按回车键继续...")
    else:
        print("\n所有依赖库已准备就绪！")

# 在程序开始时检查依赖
print("检查程序依赖...")
check_and_install_dependencies()

# 导入所需的库
import base58 # type: ignore
import os
import random
import threading
import time
from solders.keypair import Keypair  # 改用 solders.keypair
from mnemonic import Mnemonic  # 导入助记词生成器

# 全局变量与同步事件
found_event = threading.Event()         # 用于通知所有线程匹配数量达到目标
found_keypairs = []                     # 用于保存找到的多个 Keypair
attempts = 0                            # 全局尝试次数计数
attempts_lock = threading.Lock()        # 用于保护全局计数器的锁
found_lock = threading.Lock()           # 用于保护 found_keypairs 的锁

def check_vanity_pattern(pubkey: str, pattern: str, match_type: str = 'prefix') -> bool:
    """
    检查公钥是否匹配指定的靓号模式
    """
    if match_type == 'prefix':
        return pubkey.startswith(pattern)
    elif match_type == 'suffix':
        return pubkey.endswith(pattern)
    elif match_type == 'contain':
        return pattern in pubkey
    elif match_type == 'repeat':
        return any(pattern * i in pubkey for i in range(2, 5))
    elif match_type == 'both':  # 新增前缀+后缀匹配
        prefix, suffix = pattern.split(',')  # 使用逗号分隔前缀和后缀
        return pubkey.startswith(prefix) and pubkey.endswith(suffix)
    return False

def monitor_count():
    """
    监控线程：每隔一段时间在同一行打印当前全局尝试次数（不换行）。
    """
    while not found_event.is_set():
        with attempts_lock:
            current_attempts = attempts
        sys.stdout.write(f"\r已尝试次数: {current_attempts}")
        sys.stdout.flush()
        time.sleep(0.2)
    with attempts_lock:
        current_attempts = attempts
    sys.stdout.write(f"\r已尝试次数: {current_attempts}")
    sys.stdout.flush()

def generate_mnemonic_from_private_key(private_key_bytes):
    """
    从私钥生成助记词
    """
    mnemo = Mnemonic("english")
    # 使用私钥的前16字节作为熵来生成助记词
    entropy = private_key_bytes[:16]
    return mnemo.to_mnemonic(entropy)

def worker(pattern: str, target_count: int, match_type: str = 'prefix'):
    """
    线程工作函数：不断生成 Keypair，
    如果找到公钥匹配指定模式，则记录该 Keypair并立即打印匹配信息。
    """
    global attempts, found_keypairs
    while not found_event.is_set():
        keypair = Keypair()
        pubkey = str(keypair.pubkey())
        
        with attempts_lock:
            attempts += 1
            current_attempts = attempts
            
        if check_vanity_pattern(pubkey, pattern, match_type):
            with found_lock:
                if len(found_keypairs) < target_count:
                    found_keypairs.append(keypair)
                    mnemonic = generate_mnemonic_from_private_key(bytes(keypair.secret()))
                    print(f"\n找到匹配地址 {len(found_keypairs)}:")
                    print(f"公钥: {pubkey}")
                    print(f"私钥: {base58.b58encode(bytes(keypair.secret())).decode('utf-8')}")
                    print(f"助记词: {mnemonic}")
                    print(f"尝试次数: {current_attempts}", flush=True)
                    if len(found_keypairs) >= target_count:
                        found_event.set()

def generate_vanity_addresses(pattern: str, target_count: int, match_type: str = 'prefix', num_threads: int = 4) -> list:
    """
    使用多线程生成靓号地址。
    """
    global found_keypairs, attempts, found_event
    found_keypairs = []
    attempts = 0
    found_event.clear()
    
    threads = []
    monitor_thread = threading.Thread(target=monitor_count, name="Monitor")
    monitor_thread.start()

    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(pattern, target_count, match_type), name=f"Worker-{i+1}")
        t.start()
        threads.append(t)

    found_event.wait()
    
    for t in threads:
        t.join()
    monitor_thread.join()
    
    return found_keypairs

def save_keypair_to_file(keypair: Keypair, pattern: str, idx: int, mode: str = 'a'):
    """
    将 Keypair 保存到指定文件中，包括助记词。
    mode='a' 表示追加模式
    """
    filename = "vanity_keypairs.txt"  # 使用固定的文件名
    with open(filename, mode) as f:
        pubkey = str(keypair.pubkey())
        privkey = base58.b58encode(bytes(keypair.secret())).decode('utf-8')
        mnemonic = generate_mnemonic_from_private_key(bytes(keypair.secret()))
        # 使用更简洁的格式，添加助记词
        f.write(f"[{idx}] {pattern}\n")
        f.write(f"Public Key: {pubkey}\n")
        f.write(f"Private Key: {privkey}\n")
        f.write(f"Mnemonic: {mnemonic}\n")
        f.write("-" * 80 + "\n")

def print_menu():
    """
    打印主菜单
    """
    print("\n=== Solana 靓号生成器 ===")
    print("1. 生成前缀靓号")
    print("2. 生成后缀靓号")
    print("3. 生成包含特定数字的靓号")
    print("4. 生成重复数字靓号")
    print("5. 生成前缀+后缀靓号")  # 新增选项
    print("0. 退出程序")
    print("=====================")

def get_valid_input(prompt: str, input_type=str):
    """
    获取并验证用户输入
    """
    while True:
        try:
            user_input = input(prompt)
            if input_type == int:
                return int(user_input)
            return user_input
        except ValueError:
            print("输入无效，请重试！")

def main_menu():
    """
    主菜单程序
    """
    # 默认使用最高线程数
    thread_count = os.cpu_count() or 8
    
    while True:
        print_menu()
        choice = get_valid_input("请选择功能 (0-5): ", int)
        
        if choice == 0:
            print("感谢使用，再见！")
            break
            
        if choice not in [1, 2, 3, 4, 5]:
            print("无效的选择，请重试！")
            continue
            
        # 根据选择获取输入
        if choice == 5:
            prefix = get_valid_input("请输入要匹配的前缀: ")
            suffix = get_valid_input("请输入要匹配的后缀: ")
            pattern = f"{prefix},{suffix}"
        else:
            pattern = get_valid_input("请输入要匹配的数字或字符: ")
            
        target_count = get_valid_input("请输入要生成的地址数量: ", int)
        
        # 根据选择执行相应功能
        match_type = {
            1: 'prefix',
            2: 'suffix',
            3: 'contain',
            4: 'repeat',
            5: 'both'
        }[choice]
        
        print(f"\n开始生成靓号地址，请稍候...\n")
        
        try:
            keypairs = generate_vanity_addresses(
                pattern, 
                target_count, 
                match_type=match_type,
                num_threads=thread_count
            )
            
            print("\n=== 生成结果 ===")
            # 第一个地址时使用写入模式，之后使用追加模式
            for idx, keypair in enumerate(keypairs, start=1):
                print(f"\n匹配地址 {idx}:")
                print(f"公钥: {keypair.pubkey()}")
                print(f"私钥: {base58.b58encode(bytes(keypair.secret())).decode('utf-8')}")
                
                # 保存到同一个文件
                mode = 'w' if idx == 1 else 'a'  # 第一个地址时覆盖文件，之后追加
                save_keypair_to_file(keypair, pattern, idx, mode)
            
            print("\n生成完成！所有地址已保存到 vanity_keypairs.txt")
            
        except Exception as e:
            print(f"\n生成过程中出现错误: {str(e)}")
        
        input("\n按回车键继续...")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n程序已被用户中断。")
    except Exception as e:
        print(f"\n程序发生错误: {str(e)}")
