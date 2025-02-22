import platform
import subprocess
import sys
from importlib.metadata import distributions
import base64
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from pathlib import Path
import time
import os
import argparse
import shutil

def detect_os() -> str:
    """检测操作系统类型"""
    system = platform.system().lower()
    if 'windows' in system:
        return 'windows'
    elif 'linux' in system:
        return 'linux'
    else:
        return 'other'

def check_system_dependencies():
    """检查并安装系统级依赖"""
    if detect_os() == 'linux':
        try:
            print("\n正在检查系统依赖...")
            # 准备安装命令
            commands = [
                "sudo apt-get update",
                "sudo apt-get install -y build-essential python3-dev",
                "sudo apt-get install -y pkg-config libssl-dev",
                "sudo apt-get install -y python3-pip"
            ]
            
            # 执行安装命令
            for cmd in commands:
                print(f"\n执行: {cmd}")
                result = subprocess.run(cmd.split(), capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"❌ 命令执行失败: {result.stderr}")
                    return False
                print("✅ 执行成功")
            
            # 安装 Rust
            if not Path.home().joinpath('.cargo/env').exists():
                print("\n正在安装 Rust...")
                rust_install = subprocess.run(
                    "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                    shell=True,
                    capture_output=True,
                    text=True
                )
                if rust_install.returncode != 0:
                    print(f"❌ Rust 安装失败: {rust_install.stderr}")
                    return False
                print("✅ Rust 安装成功")
                
                # 更新环境变量
                cargo_env = str(Path.home().joinpath('.cargo/env'))
                os.environ["PATH"] = f"{os.environ['PATH']}:{str(Path.home().joinpath('.cargo/bin'))}"
                
                # 使用bash执行source命令
                try:
                    subprocess.run(f"bash -c 'source {cargo_env}'", shell=True, check=True)
                    print("✅ Rust环境变量已更新")
                except subprocess.CalledProcessError as e:
                    print(f"⚠️ Rust环境变量更新失败: {e}")
                    # 继续执行，因为我们已经更新了PATH
            
            # 验证 Rust 安装
            try:
                subprocess.run(["cargo", "--version"], check=True, capture_output=True)
                print("✅ Rust 安装验证成功")
            except subprocess.CalledProcessError:
                print("❌ Rust 安装验证失败")
                return False
            
            return True
            
        except Exception as e:
            print(f"❌ 安装系统依赖失败: {str(e)}")
            return False
    return True

def install_package(package_name):
    """安装Python包"""
    print(f"正在安装 {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"✅ {package_name} 安装成功！")
    except subprocess.CalledProcessError as e:
        print(f"❌ {package_name} 安装失败: {str(e)}")
        sys.exit(1)

def check_and_install_dependencies():
    """完全自动化的依赖安装"""
    def is_venv():
        return (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or \
               (hasattr(sys, 'real_prefix') and sys.real_prefix != sys.prefix)
    
    # 自动创建虚拟环境
    if not is_venv():
        print("\n🚀 开始全自动环境配置...")
        try:
            # 修改1: 使用当前目录而不是/opt目录
            project_dir = Path.cwd()
            project_dir.mkdir(exist_ok=True, parents=True)
            os.chdir(project_dir)
            print(f"📁 工作目录: {project_dir}")

            # 修改2: 添加python3-venv到系统依赖
            if detect_os() == 'linux':
                print("🛠 安装系统依赖...")
                subprocess.run(['apt-get', 'update', '-qq'], check=True)
                subprocess.run(['apt-get', 'install', '-y', 
                              'python3-dev', 'python3-venv', 'libssl-dev',  # 确保包含python3-venv
                              'build-essential', 'pkg-config', 'curl'], check=True)

            # 修改3: 在当前目录创建虚拟环境
            venv_path = project_dir / 'venv'
            if venv_path.exists():
                print("♻️ 清理旧虚拟环境...")
                shutil.rmtree(venv_path)
            print("🐍 创建新虚拟环境...")
            subprocess.run([sys.executable, '-m', 'venv', str(venv_path)], check=True)

            # 修改4: 获取正确的Python路径
            venv_python = str(venv_path / 'bin' / 'python') 

            # 安装系统依赖
            if detect_os() == 'linux':
                print("🛠 安装系统依赖...")
                subprocess.run(['sudo', 'apt-get', 'update', '-qq'], check=True)
                subprocess.run(['sudo', 'apt-get', 'install', '-y', 
                              'python3-dev', 'python3-venv', 'libssl-dev',
                              'build-essential', 'pkg-config', 'curl'], check=True)
            
            # 安装Rust
            print("🦀 安装Rust工具链...")
            rust_install = subprocess.run(
                "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                shell=True,
                capture_output=True,
                text=True
            )
            if rust_install.returncode != 0:
                print(f"❌ Rust安装失败: {rust_install.stderr}")
                sys.exit(1)
                
            # 设置环境变量
            os.environ["PATH"] = f"{os.environ['PATH']}:{str(Path.home() / '.cargo/bin')}"
            
            # 安装Python依赖
            print("📦 安装Python依赖...")
            subprocess.run(
                [venv_python, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'],
                check=True
            )
            subprocess.run([
                venv_python, '-m', 'pip', 'install', '-q',
                'setuptools-rust==1.7.0',
                'construct==2.10.68',
                'base58==2.1.1',
                'PyNaCl==1.5.0',
                'solana==0.25.1',
                'solders'
            ], check=True)
            
            # 重启程序
            print("✅ 环境配置完成！正在重启程序...")
            os.execl(venv_python, venv_python, *sys.argv)
            
        except Exception as e:
            print(f"❌ 自动安装失败: {str(e)}")
            sys.exit(1)

    # 检查Python包依赖
    required_packages = {'requests', 'solders', 'solana'}
    installed_packages = {dist.metadata['Name'] for dist in distributions()}
    
    # 自动安装缺失包
    for pkg in required_packages - installed_packages:
        install_package(pkg)

# 在脚本开始时调用依赖检查
check_and_install_dependencies()

# 检查依赖
# print("检查程序依赖...")
# check_and_install_dependencies()

try:
    # 尝试导入 solana 相关库
    from solders.pubkey import Pubkey
    from solana.rpc.api import Client
    from solana.rpc.commitment import Commitment
    print("✅ Solana 库导入成功")
except ImportError as e:
    print(f"❌ Solana 库导入失败: {str(e)}")
    print("\n尝试重新安装依赖:")
    print("""
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install construct>=2.10.68
pip install base58>=2.1.1
pip install PyNaCl>=1.4.0
pip install solana==0.25.1
pip install solders
""")
    # sys.exit(1) # Remove the exit call, as the installation is handled above

class TokenPlatformAnalyzer:
    """代币平台分析器"""
    
    # 已知发币平台的特征
    KNOWN_PLATFORMS = {
        "Pump.fun": {  # 添加 Pump.fun 平台特征
            "creator": "PumpFunx3gZoPvPqbCiPvGfcvwHhqKS1TzpGevYdtmW",  # Pump.fun 官方地址
            "patterns": ["pump", "fun"],
            "instruction_patterns": ["pump", "launch"]
        },
        "Jupiter": {
            "creator": "JUP2jxvXaqu7NQY1GmNF4m1vodw12LVXYxbFL2uJvfo",
            "patterns": ["jupiter", "JUP"],
            "instruction_patterns": ["swap", "route"]
        },
        "Raydium": {
            "creator": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "patterns": ["raydium", "RAY"],
            "instruction_patterns": ["initialize_pool", "swap", "deposit"]
        },
        "Serum": {
            "creator": "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",
            "patterns": ["serum", "SRM"],
            "instruction_patterns": ["new_order", "match_orders"]
        },
        "Solana Program Library (SPL)": {
            "creator": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "patterns": ["spl", "token-program"],
            "instruction_patterns": ["initialize_mint", "transfer"]
        },
        "Magic Eden": {
            "creator": "M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K",
            "patterns": ["magiceden", "ME"],
            "instruction_patterns": ["list", "delist", "buy", "sell"]
        }
    }

    @staticmethod
    def analyze_platform(contract_data: dict) -> dict:
        """分析合约可能来自的发币平台"""
        results = []
        warnings = []
        
        # 获取合约数据和交互信息
        contract_address = contract_data.get('合约地址', '')
        contract_code = str(contract_data.get('源代码', {}))
        creator = contract_data.get('程序所有者', '')
        recent_txs = contract_data.get('最近交易', [])
        
        # 检查是否包含 "pump" 关键字但不是 Pump.fun 平台
        if "pump" in contract_address.lower():
            is_real_pump = False
            for platform_name, platform_info in TokenPlatformAnalyzer.KNOWN_PLATFORMS.items():
                if platform_name == "Pump.fun" and (
                    creator == platform_info['creator'] or
                    any(pattern.lower() in str(recent_txs).lower() for pattern in platform_info['instruction_patterns'])
                ):
                    is_real_pump = True
                    break
            
            if not is_real_pump:
                warnings.append({
                    "type": "fake_pump",
                    "message": (
                        "⚠️ 警告: 该代币地址包含'pump'字样但不是官方Pump.fun平台发行的代币\n"
                        "  • 官方Pump.fun地址: PumpFunx3gZoPvPqbCiPvGfcvwHhqKS1TzpGevYdtmW\n"
                        "  • 当前代币创建者: {}\n"
                        "  • 这可能是一个仿冒Pump.fun的欺诈代币"
                    ).format(creator),
                    "risk_level": "high"
                })
        
        # 原有的平台分析逻辑
        for platform_name, platform_info in TokenPlatformAnalyzer.KNOWN_PLATFORMS.items():
            confidence = 0
            reasons = []
            
            if creator == platform_info['creator']:
                confidence += 0.6
                reasons.append("创建者地址匹配")
            
            for pattern in platform_info['patterns']:
                if pattern.lower() in contract_code.lower():
                    confidence += 0.2
                    reasons.append(f"发现平台特征: {pattern}")
            
            for tx in recent_txs:
                for pattern in platform_info['instruction_patterns']:
                    if pattern.lower() in str(tx).lower():
                        confidence += 0.1
                        reasons.append(f"交易包含特征指令: {pattern}")
            
            if confidence > 0:
                results.append({
                    "platform_name": platform_name,
                    "confidence": min(confidence, 1.0),
                    "reasons": list(set(reasons))
                })
        
        return {
            "platforms": sorted(results, key=lambda x: x['confidence'], reverse=True),
            "warnings": warnings
        }

class VulnerabilityAnalyzer:
    """合约漏洞分析器"""
    
    VULNERABILITY_PATTERNS = {
        "重入攻击风险": {
            "patterns": [
                "invoke_signed",
                "invoke_unchecked",
                "cross_program_invocation"
            ],
            "description": "合约中存在跨程序调用，可能存在重入攻击风险"
        },
        "整数溢出风险": {
            "patterns": [
                "unchecked_math",
                "wrapping_add",
                "wrapping_sub",
                "wrapping_mul"
            ],
            "description": "合约中可能存在整数溢出风险"
        },
        "权限控制缺失": {
            "patterns": [
                "system_program::transfer",
                "token::transfer",
                "without_signer_check",
                "skip_authorization"
            ],
            "description": "合约可能缺少适当的权限控制"
        },
        "账户验证不足": {
            "patterns": [
                "account_info",
                "without_owner_check",
                "without_account_validation"
            ],
            "description": "合约可能缺少充分的账户验证"
        },
        "不安全的随机数": {
            "patterns": [
                "clock::slot",
                "clock::unix_timestamp",
                "block::slot"
            ],
            "description": "使用了可预测的随机数来源"
        },
        "资金锁定风险": {
            "patterns": [
                "close_account",
                "self_transfer",
                "without_withdraw_function"
            ],
            "description": "合约可能存在资金锁定风险"
        }
    }
    
    CRITICAL_FUNCTIONS = {
        "token::transfer": "代币转账函数",
        "system_program::transfer": "SOL转账函数",
        "initialize": "初始化函数",
        "upgrade": "升级函数",
        "set_authority": "设置权限函数",
        "close_account": "关闭账户函数"
    }

    @staticmethod
    def analyze_vulnerabilities(contract_data: dict) -> dict:
        """分析合约潜在漏洞"""
        results = {
            "high_risk": [],
            "medium_risk": [],
            "low_risk": [],
            "critical_functions": []
        }
        
        # 获取合约代码
        contract_code = ""
        if contract_data.get('源代码'):
            contract_code = str(contract_data['源代码'])
        elif contract_data.get('字节码'):
            contract_code = str(contract_data['字节码'])
        
        # 检查关键函数
        for func_pattern, func_desc in VulnerabilityAnalyzer.CRITICAL_FUNCTIONS.items():
            if func_pattern.lower() in contract_code.lower():
                results["critical_functions"].append({
                    "function": func_desc,
                    "pattern": func_pattern
                })

        # 检查漏洞模式
        for vuln_name, vuln_info in VulnerabilityAnalyzer.VULNERABILITY_PATTERNS.items():
            matched_patterns = []
            for pattern in vuln_info["patterns"]:
                if pattern.lower() in contract_code.lower():
                    matched_patterns.append(pattern)
            
            if matched_patterns:
                risk_level = "high_risk"
                if "transfer" in str(matched_patterns) or "authority" in str(matched_patterns):
                    risk_level = "high_risk"
                elif "unchecked" in str(matched_patterns):
                    risk_level = "medium_risk"
                else:
                    risk_level = "low_risk"
                
                results[risk_level].append({
                    "name": vuln_name,
                    "description": vuln_info["description"],
                    "matched_patterns": matched_patterns
                })

        return results

    @staticmethod
    def analyze_security_score(info: dict) -> dict:
        """计算合约安全评分并返回详细扣分原因"""
        score = 100.0
        deductions = []
        
        # 基础漏洞扣分
        if info.get('漏洞分析'):
            vuln = info['漏洞分析']
            if vuln.get('high_risk'):
                deductions.append(("高风险漏洞", len(vuln['high_risk']) * 20))
            if vuln.get('medium_risk'):
                deductions.append(("中风险漏洞", len(vuln['medium_risk']) * 10))
            if vuln.get('low_risk'):
                deductions.append(("低风险漏洞", len(vuln['low_risk']) * 5))
        
        # 权限风险扣分
        if info.get('字节码'):
            bytecode_info = info.get('字节码解析结果', {})
            if bytecode_info.get('铸币权限') != "0" * 64:
                deductions.append(("保留铸币权限", 30))
            if bytecode_info.get('冻结权限') != "0" * 64:
                deductions.append(("保留冻结权限", 20))
        
        # 交易模式风险扣分
        tx_analysis = info.get('交易记录分析', {})
        if "机器人操作" in str(tx_analysis.get('风险提示', [])):
            deductions.append(("机器人操作风险", 15))
        if "密集交易模式" in str(tx_analysis.get('风险提示', [])):
            deductions.append(("密集交易风险", 10))
        
        # 平台风险扣分
        platform_analysis = info.get('发币平台分析', {})
        if platform_analysis.get('warnings'):
            if any("仿冒" in w['message'] for w in platform_analysis['warnings']):
                deductions.append(("仿冒代币风险", 40))
        
        # 应用扣分
        total_deduction = 0
        for reason, points in deductions:
            total_deduction += points
        
        score = max(0.0, min(100.0, score - total_deduction))
        
        return {
            "score": score,
            "deductions": deductions,
            "risk_level": "高风险" if score < 60 else "中风险" if score < 80 else "低风险"
        }

def get_risk_level_icon(risk_level: str) -> str:
    """获取风险等级图标"""
    return {
        "high_risk": "🔴",
        "medium_risk": "🟡",
        "low_risk": "🟢"
    }.get(risk_level, "⚪")

def get_stats(info: dict) -> dict:
    """生成统计信息"""
    return {
        "交易总数": len(info.get('最近交易', [])),
        "高风险漏洞数": len(info.get('漏洞分析', {}).get('high_risk', [])),
        "中风险漏洞数": len(info.get('漏洞分析', {}).get('medium_risk', [])),
        "低风险漏洞数": len(info.get('漏洞分析', {}).get('low_risk', []))
    }

def generate_security_suggestions(info: dict) -> list:
    """生成安全建议"""
    suggestions = []
    if info.get('漏洞分析', {}).get('high_risk'):
        suggestions.append("⚠️ 建议立即修复高风险漏洞")
    
    # 修改这里的安全评分判断
    security_score = info.get('安全评分', {}).get('score', 100)
    if security_score < 60:
        suggestions.append("⚠️ 建议进行全面的安全审计")
    
    if info.get('漏洞分析', {}).get('medium_risk'):
        suggestions.append("⚠️ 建议关注并计划修复中风险漏洞")
    if not info.get('源代码'):
        suggestions.append("⚠️ 建议公开源代码以提高透明度")
    return suggestions

class ContractAnalyzer:
    def __init__(self):
        """初始化分析器，使用公共RPC节点"""
        self.rpc_endpoints = [
            # 添加你的HTTP节点
            "http://your-http-node-1:8899",
            "http://your-http-node-2:8899",
            # 保留一些公共节点作为备用
            "https://api.mainnet-beta.solana.com",
            "https://rpc.ankr.com/solana"
        ]
        self.client = None
        self.api_keys = load_api_keys()  # 加载保存的API密钥
        self.connect_to_best_rpc()
        
    def connect_to_best_rpc(self):
        """连接到响应最快的RPC节点"""
        print("\n正在尝试连接RPC节点...")
        timeout = 30  # 统一设置更长的超时时间
        
        for endpoint in self.rpc_endpoints:
            try:
                print(f"尝试连接: {endpoint}")
                
                # 在测试节点可用性时添加更完整的请求头
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                # 测试节点可用性
                response = requests.post(
                    endpoint, 
                    json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                    headers=headers,
                    timeout=timeout
                )
                
                if response.status_code != 200:
                    print(f"❌ 端点响应异常: {response.status_code}")
                    continue
                    
                # 初始化客户端
                self.client = Client(endpoint, timeout=timeout)
                
                # 测试连接
                slot = self.client.get_slot()
                print(f"✅ 连接成功! 当前slot: {slot}")
                return
                
            except Exception as e:
                print(f"❌ 连接失败: {str(e)}")
                continue
        
        raise Exception("无法连接到任何RPC节点，请检查网络连接或稍后重试")

    def get_contract_bytecode(self, contract_address: str) -> Optional[str]:
        """获取合约字节码"""
        try:
            pubkey = Pubkey.from_string(contract_address)
            account_info = self.client.get_account_info(pubkey)
            if account_info.value and account_info.value.data:
                return base64.b64encode(account_info.value.data).decode('utf-8')
            return None
        except Exception as e:
            print(f"获取字节码失败: {str(e)}")
            return None

    def get_contract_source(self, contract_address: str) -> Optional[Dict[str, Any]]:
        """从多个来源尝试获取合约源代码"""
        sources = {
            "explorer": f"https://api.explorer.solana.com/v1/account/{contract_address}/parsed-account-data",
            "solscan": f"https://api.solscan.io/account/source?address={contract_address}",
            "solana_fm": f"https://api.solana.fm/v0/accounts/{contract_address}/source"
        }
        
        for source_name, url in sources.items():
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data and not isinstance(data, str):
                        return {
                            "source": source_name,
                            "data": data
                        }
            except Exception:
                continue
        return None

    def get_program_info(self, contract_address: str) -> dict:
        """获取合约详细信息"""
        try:
            if not self.client:
                self.connect_to_best_rpc()
            
            pubkey = Pubkey.from_string(contract_address)
            
            # 获取账户信息
            account_info = self.client.get_account_info(pubkey)
            if not account_info.value:
                return {"error": "未找到合约账户"}
            
            account_data = account_info.value
            
            # 获取最近的交易记录
            recent_txs = self.client.get_signatures_for_address(
                pubkey, 
                limit=10
            ).value
            
            # 获取合约源代码
            contract_source = self.get_contract_source(contract_address)
            
            # 获取字节码（如果没有源代码）
            bytecode = None if contract_source else self.get_contract_bytecode(contract_address)
            
            # 获取关联的代币账户
            token_accounts = self.get_token_accounts_by_owner(contract_address)
            
            # 基本信息
            info = {
                "合约地址": str(pubkey),
                "程序所有者": str(account_data.owner),
                "账户余额": account_data.lamports / 10**9,  # 转换为 SOL
                "是否可执行": account_data.executable,
                "数据大小": len(account_data.data) if account_data.data else 0,
                "最近交易数量": len(recent_txs),
                "源代码": contract_source,
                "字节码": bytecode,
                "关联代币账户": [
                    {
                        "地址": str(account["pubkey"]),
                        "数据": account["data"]
                    } for account in token_accounts
                ] if token_accounts else [],
                "最近交易": [
                    {
                        "签名": tx.signature,
                        "时间": datetime.fromtimestamp(tx.block_time).strftime("%Y-%m-%d %H:%M:%S") if tx.block_time else "未知",
                        "状态": "成功" if not tx.err else "失败"
                    } for tx in recent_txs
                ]
            }
            
            # 分析可能的发币平台
            platform_analysis = TokenPlatformAnalyzer.analyze_platform(info)
            if platform_analysis:
                info["发币平台分析"] = platform_analysis
            
            # 添加漏洞分析
            vulnerabilities = VulnerabilityAnalyzer.analyze_vulnerabilities(info)
            security_score = VulnerabilityAnalyzer.analyze_security_score(info)
            
            info.update({
                "漏洞分析": vulnerabilities,
                "安全评分": security_score
            })
            
            return info
            
        except Exception as e:
            print(f"\n获取合约信息时出错: {str(e)}")
            print(f"错误类型: {type(e)}")
            return {"error": f"分析失败: {str(e)}"}

    def analyze_transaction_patterns(self, transactions: list) -> dict:
        """分析交易模式和风险"""
        analysis = {
            "交易统计": {
                "总交易数": len(transactions),
                "成功交易": sum(1 for tx in transactions if tx["状态"] == "成功"),
                "失败交易": sum(1 for tx in transactions if tx["状态"] != "成功"),
            },
            "时间模式": {
                "最早交易": min(tx["时间"] for tx in transactions) if transactions else "无",
                "最近交易": max(tx["时间"] for tx in transactions) if transactions else "无",
            },
            "风险提示": []
        }
        
        # 分析交易时间间隔
        if len(transactions) >= 2:
            sorted_txs = sorted(transactions, key=lambda x: datetime.strptime(x["时间"], "%Y-%m-%d %H:%M:%S"))
            intervals = []
            for i in range(1, len(sorted_txs)):
                t1 = datetime.strptime(sorted_txs[i-1]["时间"], "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(sorted_txs[i]["时间"], "%Y-%m-%d %H:%M:%S")
                intervals.append((t2 - t1).total_seconds())
            
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval < 10:  # 平均间隔小于10秒
                analysis["风险提示"].append("⚠️ 警告: 交易频率异常高,可能存在机器人操作")
        
        # 分析失败率
        if analysis["交易统计"]["总交易数"] > 0:
            failure_rate = analysis["交易统计"]["失败交易"] / analysis["交易统计"]["总交易数"]
            if failure_rate > 0.3:  # 失败率超过30%
                analysis["风险提示"].append("⚠️ 警告: 交易失败率较高,可能存在合约限制或操作风险")
        
        # 分析交易模式
        if len(transactions) >= 3:
            recent_txs = transactions[:3]  # 最近3笔交易
            if all(tx["状态"] == "成功" for tx in recent_txs):
                time_diffs = []
                for i in range(1, len(recent_txs)):
                    t1 = datetime.strptime(recent_txs[i-1]["时间"], "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(recent_txs[i]["时间"], "%Y-%m-%d %H:%M:%S")
                    time_diffs.append((t2 - t1).total_seconds())
                
                if all(diff < 5 for diff in time_diffs):  # 连续交易间隔小于5秒
                    analysis["风险提示"].append("⚠️ 警告: 检测到密集交易模式,可能是抢注或机器人操作")
        
        return analysis

    def convert_to_utc8(self, timestamp: str) -> str:
        """将时间转换为UTC+8"""
        try:
            # 解析原始时间
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            # 添加8小时
            dt = dt + timedelta(hours=8)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return timestamp

    def generate_report(self, contract_address: str) -> str:
        """生成分析报告"""
        try:
            info = self.get_program_info(contract_address)
            if "error" in info:
                return f"❌ 分析失败: {info['error']}"
            
            # 生成报告内容
            report = [
                "=" * 50,
                "🔍 Solana 合约分析报告",
                "=" * 50,
                f"📅 生成时间: {(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)",
                f"⏱️ 分析耗时: {(datetime.now() - datetime.now()).total_seconds():.2f}秒",
                
                "\n📋 基本信息:",
                f"📍 合约地址: {info['合约地址']}",
                f"👤 程序所有者: {info['程序所有者']}",
                f"💰 账户余额: {info['账户余额']} SOL",
                f"⚙️ 是否可执行: {'是' if info['是否可执行'] else '否'}",
                f"📦 数据大小: {info['数据大小']} 字节",
                
                "\n📊 统计信息:",
                f"总交易数: {get_stats(info)['交易总数']}",
                f"漏洞总数: {sum(get_stats(info).values())}",
                "漏洞分布:",
                f"  {get_risk_level_icon('high_risk')} 高风险: {get_stats(info)['高风险漏洞数']}",
                f"  {get_risk_level_icon('medium_risk')} 中风险: {get_stats(info)['中风险漏洞数']}",
                f"  {get_risk_level_icon('low_risk')} 低风险: {get_stats(info)['低风险漏洞数']}"
            ]
            
            # 添加发币平台分析结果
            if "发币平台分析" in info:
                platform_analysis = info["发币平台分析"]
                report.append("\n🏢 发币平台分析:")
                
                # 显示预警信息
                if platform_analysis.get("warnings"):
                    report.append("\n⚠️ 重要预警:")
                    for warning in platform_analysis["warnings"]:
                        report.append(f"- {warning['message']}")
                
                # 显示平台信息
                for plat in platform_analysis.get("platforms", []):
                    report.extend([
                        f"\n可能的平台: {plat['platform_name']}",
                        f"置信度: {plat['confidence']*100:.1f}%",
                        "原因:"
                    ])
                    for reason in plat['reasons']:
                        report.append(f"  ✓ {reason}")
            
            # 添加合约代码信息
            report.append("\n📜 合约代码:")
            if info['源代码']:
                report.extend([
                    "源代码:",
                    json.dumps(info['源代码'], indent=2, ensure_ascii=False)
                ])
            elif info['字节码']:
                report.extend([
                    "字节码:",
                    info['字节码'],
                    "\n🔍 字节码解析结果:"
                ])
                # 解析字节码
                bytecode_info = self.decode_token_bytecode(info['字节码'])
                if "error" not in bytecode_info:
                    # 计算实际供应量
                    supply = bytecode_info['总供应量']
                    decimals = bytecode_info['代币精度']
                    actual_supply = supply / (10 ** decimals)
                    
                    report.extend([
                        f"📊 代币精度: {decimals}",
                        f"💰 原始供应量: {supply}",
                        f"💎 实际流通量: {actual_supply:,.2f} (考虑精度后)",
                        f"✅ 初始化状态: {'已初始化' if bytecode_info['是否已初始化'] else '未初始化'}",
                        f"🔑 铸币权限: {bytecode_info['铸币权限']}",
                        f"❄️ 冻结权限: {bytecode_info['冻结权限']}"
                    ])
                    
                    # 添加权限分析
                    report.append("\n⚠️ 权限风险分析:")
                    if bytecode_info['铸币权限'] != "0" * 64:
                        report.append("- ⚠️ 警告: 合约保留铸币权限,存在增发风险")
                    else:
                        report.append("- ✅ 铸币权限已禁用,无增发风险")
                        
                    if bytecode_info['冻结权限'] != "0" * 64:
                        report.append("- ⚠️ 警告: 合约保留冻结权限,可能限制代币转账")
                    else:
                        report.append("- ✅ 冻结权限已禁用,转账不受限制")
                else:
                    report.append(f"❌ {bytecode_info['error']}")
            else:
                report.append("❌ 未能获取合约代码")
            
            # 添加交易记录分析
            report.append("\n📜 最近交易记录分析:")
            tx_analysis = self.analyze_transaction_patterns(info['最近交易'])
            
            report.extend([
                f"📊 交易统计:",
                f"  • 总交易数: {tx_analysis['交易统计']['总交易数']}",
                f"  • 成功交易: {tx_analysis['交易统计']['成功交易']}",
                f"  • 失败交易: {tx_analysis['交易统计']['失败交易']}",
                f"\n⏰ 时间分析 (UTC+8):",
                f"  • 最早交易: {self.convert_to_utc8(tx_analysis['时间模式']['最早交易'])}",
                f"  • 最近交易: {self.convert_to_utc8(tx_analysis['时间模式']['最近交易'])}"
            ])
            
            if tx_analysis['风险提示']:
                report.append("\n⚠️ 交易风险提示:")
                for warning in tx_analysis['风险提示']:
                    report.append(f"  • {warning}")
            
            # 添加详细交易记录
            report.append("\n📜 详细交易记录:")
            for tx in info['最近交易']:
                report.extend([
                    f"- 签名: {tx['签名']}",
                    f"  ⏰ 时间: {self.convert_to_utc8(tx['时间'])} (UTC+8)",
                    f"  状态: {'✅ 成功' if tx['状态'] == '成功' else '❌ 失败'}"
                ])
            
            # 添加安全分析
            security_analysis = VulnerabilityAnalyzer.analyze_security_score(info)
            report.extend([
                "\n🛡️ 安全分析:",
                f"安全评分: {security_analysis['score']:.1f}/100.0 ({security_analysis['risk_level']})",
                "\n扣分详情:"
            ])
            
            for reason, points in security_analysis['deductions']:
                report.append(f"  • {reason}: -{points}分")
            
            # 添加安全建议
            suggestions = generate_security_suggestions(info)
            if suggestions:
                report.extend([
                    "\n💡 安全建议:",
                    *suggestions
                ])
            
            report.append("\n" + "=" * 50)
            report.append("🏁 报告结束")
            report.append("=" * 50)
            
            return "\n".join(report)
            
        except Exception as e:
            return f"生成报告失败: {str(e)}"

    def get_token_accounts_by_owner(self, pubkey: str) -> list:
        """获取代币账户信息的优化版本"""
        try:
            token_accounts = self.client.get_token_accounts_by_owner(
                Pubkey.from_string(pubkey),
                {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
            )
            
            if not token_accounts or not hasattr(token_accounts, 'value'):
                return []
            
            result = []
            for account in token_accounts.value:
                try:
                    account_data = {
                        "pubkey": str(account.pubkey),
                        "data": base64.b64encode(account.account.data).decode('utf-8') if account.account.data else None
                    }
                    result.append(account_data)
                except Exception as e:
                    print(f"处理代币账户数据时出错: {str(e)}")
                    continue
                
            return result
        except Exception as e:
            print(f"获取代币账户列表时出错: {str(e)}")
            return []

    def decode_token_bytecode(self, bytecode: str) -> dict:
        """解析代币字节码"""
        try:
            # Base64 解码
            raw_data = base64.b64decode(bytecode)
            
            # 解析基本参数
            token_info = {
                "mint_authority_option": int.from_bytes(raw_data[0:4], 'little'),
                "mint_authority": raw_data[4:36].hex(),
                "supply": int.from_bytes(raw_data[36:44], 'little'),
                "decimals": raw_data[44],
                "is_initialized": bool(raw_data[45]),
                "freeze_authority_option": int.from_bytes(raw_data[46:50], 'little'),
                "freeze_authority": raw_data[50:82].hex() if len(raw_data) >= 82 else None
            }
            
            return {
                "代币精度": token_info["decimals"],
                "总供应量": token_info["supply"],
                "是否已初始化": token_info["is_initialized"],
                "铸币权限": token_info["mint_authority"],
                "冻结权限": token_info["freeze_authority"],
            }
        except Exception as e:
            return {"error": f"字节码解析失败: {str(e)}"}

    def get_all_transactions(self, contract_address: str) -> list:
        """获取合约的所有交易记录"""
        try:
            all_txs = []
            limit = 100
            offset = 0
            
            # 获取API密钥
            api_key = self.api_keys.get('solscan') if hasattr(self, 'api_keys') else None
            if not api_key:
                print("⚠️ 未设置Solscan API密钥，请先在API管理中添加密钥")
                return []
            
            print("\n正在从Solscan获取历史交易记录...")
            
            while True:
                # 使用Solscan API获取交易
                url = f"https://public-api.solscan.io/account/transactions"
                params = {
                    "account": contract_address,
                    "limit": limit,
                    "offset": offset
                }
                headers = {
                    "token": api_key,
                    "Accept": "application/json"
                }
                
                # 处理API限制
                if response.status_code == 429:
                    print("⚠️ API请求达到限制，等待5秒后重试...")
                    time.sleep(5)
                    continue
                
                if response.status_code != 200:
                    print(f"❌ API请求失败: {response.status_code}")
                    print(f"响应内容: {response.text}")
                    break
                    
                transactions = response.json()
                if not transactions or len(transactions) == 0:
                    break
                    
                for tx in transactions:
                    try:
                        # 解析交易详情
                        tx_data = {
                            "签名": tx.get("signature", ""),
                            "时间": datetime.fromtimestamp(tx.get("blockTime", 0)).strftime("%Y-%m-%d %H:%M:%S"),
                            "状态": "成功" if tx.get("status") == "Success" else "失败",
                            "区块": tx.get("slot"),
                            "手续费": float(tx.get("fee", 0)) / 10**9,
                            "交互账户": [],
                            "指令数": len(tx.get("instructions", [])),
                            "交易类型": []
                        }
                        
                        # 获取交互账户
                        if "accounts" in tx:
                            tx_data["交互账户"] = tx["accounts"]
                        
                        # 获取交易类型
                        if "instructions" in tx:
                            for inst in tx["instructions"]:
                                if "programId" in inst:
                                    tx_data["交易类型"].append(inst["programId"])
                        
                        all_txs.append(tx_data)
                        print(f"✅ 已获取交易: {tx_data['签名'][:20]}...")
                        
                    except Exception as e:
                        print(f"处理交易详情失败: {str(e)}")
                        continue
                
                print(f"已获取 {len(all_txs)} 笔交易...")
                
                # 如果返回的交易数小于limit，说明已经到最后一页
                if len(transactions) < limit:
                    break
                    
                offset += limit
                
            return all_txs
            
        except Exception as e:
            print(f"获取交易记录失败: {str(e)}")
            return []

    def generate_transaction_report(self, contract_address: str) -> str:
        """生成交易分析报告"""
        try:
            print("\n开始生成交易分析报告...")
            all_txs = self.get_all_transactions(contract_address)
            
            report = [
                "=" * 50,
                "🔍 Solana 合约交易分析报告",
                "=" * 50,
                f"📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)",
                f"📍 合约地址: {contract_address}",
                f"📊 总交易数: {len(all_txs)}",
                "\n=== 交易统计 ===",
                f"✅ 成功交易: {sum(1 for tx in all_txs if tx['状态'] == '成功')}",
                f"❌ 失败交易: {sum(1 for tx in all_txs if tx['状态'] == '失败')}",
                f"💰 总手续费: {sum(tx['手续费'] for tx in all_txs):.4f} SOL",
                "\n=== 时间分布 ===",
            ]
            
            # 按时间排序
            all_txs.sort(key=lambda x: x['时间'])
            if all_txs:
                report.extend([
                    f"最早交易: {all_txs[0]['时间']}",
                    f"最近交易: {all_txs[-1]['时间']}"
                ])
                
                # 分析交易频率
                time_diffs = []
                for i in range(1, len(all_txs)):
                    t1 = datetime.strptime(all_txs[i-1]['时间'], "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(all_txs[i]['时间'], "%Y-%m-%d %H:%M:%S")
                    time_diffs.append((t2 - t1).total_seconds())
                
                if time_diffs:
                    avg_interval = sum(time_diffs) / len(time_diffs)
                    report.append(f"平均交易间隔: {avg_interval:.2f} 秒")
                    
                    # 检测高频交易
                    high_freq_count = sum(1 for diff in time_diffs if diff < 5)
                    if high_freq_count > 0:
                        report.append(f"\n⚠️ 发现 {high_freq_count} 笔高频交易(间隔<5秒)")
            
            # 详细交易记录
            report.extend([
                "\n=== 详细交易记录 ===",
                "(按时间顺序排列)\n"
            ])
            
            for tx in all_txs:
                report.extend([
                    f"交易签名: {tx['签名']}",
                    f"时间: {tx['时间']}",
                    f"状态: {'✅ 成功' if tx['状态'] == '成功' else '❌ 失败'}",
                    f"区块: {tx['区块']}",
                    f"手续费: {tx['手续费']:.6f} SOL",
                    f"指令数: {tx['指令数']}",
                    f"交互账户: {', '.join(tx['交互账户'][:5])}{'...' if len(tx['交互账户']) > 5 else ''}",
                    "-" * 50
                ])
            
            return "\n".join(report)
            
        except Exception as e:
            return f"生成交易报告失败: {str(e)}"

    def save_transaction_report(self, contract_address: str) -> str:
        """保存交易分析报告"""
        report = self.generate_transaction_report(contract_address)
        
        # 使用pathlib处理路径
        reports_dir = Path("transaction_reports")
        reports_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        clean_address = "".join(c for c in contract_address if c.isalnum() or c in ('_', '-'))
        filename = reports_dir / f"tx_analysis_{clean_address[:8]}_{timestamp}.txt"
        
        # 根据系统调整编码
        encoding = 'utf-8-sig' if detect_os() == 'windows' else 'utf-8'
        
        with open(filename, 'w', encoding=encoding) as f:
            f.write(report)
        
        return str(filename)

def save_report(report: str, contract_address: str, format: str = 'txt'):
    """跨平台保存报告"""
    # 清理非法文件名字符
    clean_address = "".join(c for c in contract_address if c.isalnum() or c in ('_', '-'))
    
    # 使用pathlib处理路径
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = f"contract_analysis_{clean_address[:8]}_{timestamp}"
    
    # 根据系统调整默认编码
    encoding = 'utf-8'
    if detect_os() == 'windows':
        encoding = 'utf-8-sig'  # 解决Windows记事本UTF-8 BOM问题
    
    filename = reports_dir / f"{base_name}.{format}"
    
    with open(filename, 'w', encoding=encoding) as f:
        f.write(report)
    return str(filename)

def print_help():
    """打印帮助信息"""
    print("""
命令行参数:
  -h, --help            显示帮助信息
  -a, --address         指定要分析的合约地址
  -o, --output          指定输出文件名（可选）

跨平台支持:
  • 自动适配Windows/Linux路径
  • Windows系统自动处理编码问题
  • 不同网络超时设置优化

示例:""")
    if detect_os() == 'windows':
        print("  py -3 solana_contract_info.py -a TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    else:
        print("  python3 solana_contract_info.py -a TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

def print_env_help():
    print("\n=== 跨平台环境配置 ===")
    print("1. 创建虚拟环境:")
    print("   python -m venv solana-env")
    
    if detect_os() == 'windows':
        print("2. 激活环境:")
        print("   .\\solana-env\\Scripts\\activate")
    else:
        print("2. 激活环境:")
        print("   source solana-env/bin/activate")
    
    print("3. 安装依赖:")
    print("   pip install -r requirements.txt")

def print_menu():
    """打印主菜单"""
    print("""
=== Solana 合约分析工具 ===
1. 分析单个合约
2. 批量分析多个合约
3. 生成交易历史报告
4. 管理RPC节点
5. 管理API密钥
0. 退出程序
=====================""")

def manage_rpc_nodes(analyzer):
    """管理RPC节点"""
    while True:
        print("""
=== RPC节点管理 ===
1. 查看当前节点
2. 添加新节点
3. 测试所有节点
4. 清空节点列表
5. 恢复默认节点
0. 返回主菜单
================""")
        
        choice = input("\n请选择功能 (0-5): ").strip()
        
        if choice == '0':
            break
            
        elif choice == '1':
            print("\n当前RPC节点列表:")
            for i, endpoint in enumerate(analyzer.rpc_endpoints, 1):
                print(f"{i}. {endpoint}")
            
        elif choice == '2':
            print("\n请输入RPC节点地址（每行一个，输入空行结束）:")
            print("格式示例:")
            print("  http://64.130.50.132:8899")
            print("  https://example.com/rpc")
            new_endpoints = []
            while True:
                endpoint = input().strip()
                if not endpoint:
                    break
                # 去除可能的"HTTP:"前缀
                endpoint = endpoint.replace("HTTP:", "").replace("HTTPS:", "").strip()
                if not (endpoint.startswith('http://') or endpoint.startswith('https://')):
                    endpoint = 'http://' + endpoint
                new_endpoints.append(endpoint)
            
            if new_endpoints:
                print("\n正在测试新节点...")
                for endpoint in new_endpoints:
                    try:
                        # 测试节点连接
                        headers = {'Content-Type': 'application/json'}
                        response = requests.post(
                            endpoint,
                            json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                            headers=headers,
                            timeout=10
                        )
                        if response.status_code == 200:
                            analyzer.rpc_endpoints.append(endpoint)
                            print(f"✅ 节点添加成功: {endpoint}")
                        else:
                            print(f"❌ 节点测试失败: {endpoint} (状态码: {response.status_code})")
                    except Exception as e:
                        print(f"❌ 节点测试失败: {endpoint} ({str(e)})")
                
                print(f"\n成功添加 {len(new_endpoints)} 个节点")
            
        elif choice == '3':
            print("\n开始测试所有节点...")
            working_endpoints = []
            for endpoint in analyzer.rpc_endpoints:
                try:
                    print(f"\n测试节点: {endpoint}")
                    response = requests.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        # 尝试获取区块高度
                        client = Client(endpoint)
                        slot = client.get_slot()
                        print(f"✅ 节点正常 (当前区块: {slot})")
                        working_endpoints.append(endpoint)
                    else:
                        print("❌ 节点响应异常")
                except Exception as e:
                    print(f"❌ 测试失败: {str(e)}")
            
            # 更新节点列表
            analyzer.rpc_endpoints = working_endpoints
            print(f"\n测试完成，当前可用节点: {len(working_endpoints)} 个")
            
        elif choice == '4':
            confirm = input("\n确定要清空所有节点吗？(y/N): ").strip().lower()
            if confirm == 'y':
                analyzer.rpc_endpoints = []
                print("已清空节点列表")
            
        elif choice == '5':
            analyzer.rpc_endpoints = [
                "https://api.mainnet-beta.solana.com",
                "https://solana-mainnet.g.alchemy.com/v2/demo",
                "https://rpc.ankr.com/solana"
            ]
            print("已恢复默认节点列表")
        
        input("\n按回车键继续...")

def manage_api_keys(analyzer):
    """管理API密钥"""
    while True:
        print("""
=== API密钥管理 ===
1. 查看当前API密钥
2. 添加/更新Solscan API密钥
3. 添加/更新其他API密钥
0. 返回主菜单
================""")
        
        choice = input("\n请选择功能 (0-3): ").strip()
        
        if choice == '0':
            break
            
        elif choice == '1':
            print("\n当前API密钥:")
            if hasattr(analyzer, 'api_keys'):
                for service, key in analyzer.api_keys.items():
                    masked_key = key[:6] + "*" * (len(key) - 10) + key[-4:] if key else "未设置"
                    print(f"{service}: {masked_key}")
            else:
                print("未设置任何API密钥")
            
        elif choice == '2':
            print("\n请输入Solscan API密钥:")
            print("(从 https://docs.solscan.io/ 获取)")
            api_key = input().strip()
            if api_key:
                # 测试API密钥
                try:
                    # 使用更可靠的测试端点
                    test_url = "https://public-api.solscan.io/account/tokens"
                    params = {
                        "account": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # 使用一个已知的合约地址测试
                    }
                    headers = {
                        "token": api_key,
                        "Accept": "application/json"
                    }
                    response = requests.get(test_url, params=params, headers=headers)
                    
                    if response.status_code in [200, 429]:  # 429表示超过请求限制，但API key是有效的
                        if not hasattr(analyzer, 'api_keys'):
                            analyzer.api_keys = {}
                        analyzer.api_keys['solscan'] = api_key
                        # 保存到配置文件
                        save_api_keys(analyzer.api_keys)
                        print("✅ Solscan API密钥添加成功！")
                        
                        if response.status_code == 429:
                            print("⚠️ API请求已达到限制，但密钥是有效的")
                    else:
                        print(f"❌ API密钥测试失败: {response.status_code}")
                        print(f"响应内容: {response.text}")
                except Exception as e:
                    print(f"❌ API密钥测试失败: {str(e)}")
            
        elif choice == '3':
            print("\n支持的API服务:")
            services = ["solana_fm", "helius", "quicknode"]
            for i, service in enumerate(services, 1):
                print(f"{i}. {service}")
            
            service_idx = input("\n请选择API服务 (1-3): ").strip()
            if service_idx.isdigit() and 1 <= int(service_idx) <= len(services):
                service = services[int(service_idx) - 1]
                print(f"\n请输入{service} API密钥:")
                api_key = input().strip()
                if api_key:
                    if not hasattr(analyzer, 'api_keys'):
                        analyzer.api_keys = {}
                    analyzer.api_keys[service] = api_key
                    # 保存到配置文件
                    save_api_keys(analyzer.api_keys)
                    print(f"✅ {service} API密钥已保存")
        
        input("\n按回车键继续...")

def save_api_keys(api_keys: dict):
    """保存API密钥到配置文件"""
    config_file = Path("config.json")
    try:
        # 读取现有配置
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {}
        
        # 更新API密钥
        config['api_keys'] = api_keys
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
    except Exception as e:
        print(f"保存配置失败: {str(e)}")

def load_api_keys() -> dict:
    """从配置文件加载API密钥"""
    config_file = Path("config.json")
    try:
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('api_keys', {})
    except Exception as e:
        print(f"加载配置失败: {str(e)}")
    return {}

def check_and_setup_venv():
    """完全自动化的环境设置"""
    def is_venv():
        return (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or \
               (hasattr(sys, 'real_prefix') and sys.real_prefix != sys.prefix)

    if not is_venv():
        print("\n🚀 开始全自动环境配置...")
        try:
            # 修改1: 使用当前目录而不是/opt目录
            project_dir = Path.cwd()
            project_dir.mkdir(exist_ok=True, parents=True)
            os.chdir(project_dir)
            print(f"📁 工作目录: {project_dir}")

            # 修改2: 添加python3-venv到系统依赖
            if detect_os() == 'linux':
                print("🛠 安装系统依赖...")
                subprocess.run(['apt-get', 'update', '-qq'], check=True)
                subprocess.run(['apt-get', 'install', '-y', 
                              'python3-dev', 'python3-venv', 'libssl-dev',  # 确保包含python3-venv
                              'build-essential', 'pkg-config', 'curl'], check=True)

            # 修改3: 在当前目录创建虚拟环境
            venv_path = project_dir / 'venv'
            if venv_path.exists():
                print("♻️ 清理旧虚拟环境...")
                shutil.rmtree(venv_path)
            print("🐍 创建新虚拟环境...")
            subprocess.run([sys.executable, '-m', 'venv', str(venv_path)], check=True)

            # 修改4: 获取正确的Python路径
            venv_python = str(venv_path / 'bin' / 'python') 

            # 安装Rust工具链...
            print("🦀 安装Rust工具链...")
            rust_script = subprocess.run(
                "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs",
                shell=True, capture_output=True, text=True, check=True
            )
            subprocess.run([
                "sh", "-c", 
                rust_script.stdout.replace("--verbose", "--quiet -y") + " > /dev/null 2>&1"
            ], check=True)
            
            # 设置永久环境变量
            cargo_path = Path.home() / '.cargo' / 'env'
            with open(cargo_path, 'a') as f:
                f.write(f'\nexport PATH="$PATH:{Path.home()}/.cargo/bin"')

            # 安装Python依赖
            print("📦 安装Python依赖...")
            subprocess.run(
                [venv_python, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'],
                check=True
            )
            subprocess.run([
                venv_python, '-m', 'pip', 'install', '-q',
                'setuptools-rust==1.7.0',
                'construct==2.10.68',
                'base58==2.1.1',
                'PyNaCl==1.5.0',
                'solana==0.25.1',
                'solders'
            ], check=True)

            # 重启程序
            print("✅ 环境配置完成！正在重启程序...")
            os.execl(venv_python, venv_python, *sys.argv)

        except subprocess.CalledProcessError as e:
            print(f"❌ 安装步骤失败: {e.cmd}")
            print(f"错误输出: {e.stderr.decode()}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 意外错误: {str(e)}")
            sys.exit(1)
    else:
        try:
            from solders.pubkey import Pubkey
            from solana.rpc.api import Client
            print("✅ 环境验证通过")
        except ImportError as e:
            print(f"🔧 自动修复依赖: {str(e)}")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '-q',
                'solders==0.16.0', 'solana==0.25.1'
            ], check=True)
            # os.execl(sys.executable, sys.executable, *sys.argv)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Solana合约分析工具')
    parser.add_argument('-a', '--address', help='要分析的合约地址')
    parser.add_argument('-o', '--output', help='输出文件名')
    return vars(parser.parse_args())

def main():
    # 在程序启动时首先检查依赖
    check_and_setup_venv()
    
    print(f"\n当前操作系统: {detect_os().upper()}")
    print(f"Python版本: {platform.python_version()}")
    
    # Windows系统颜色支持
    if detect_os() == 'windows':
        try:
            import colorama
            colorama.init()
            print("已启用Windows颜色支持")
        except ImportError:
            print("提示: 安装colorama可获得更好的显示效果 (pip install colorama)")
    
    # 创建分析器实例
    analyzer = ContractAnalyzer()
    
    while True:
        print_menu()
        try:
            choice = input("\n请选择功能 (0-5): ").strip()
            
            if choice == '0':
                print("感谢使用！")
                break
                
            elif choice == '1':
                # 分析单个合约
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                    
                print("\n正在分析合约...")
                report = analyzer.generate_report(contract_address)
                print("\n" + report)
                filename = save_report(report, contract_address)
                print(f"\n报告已保存到文件: {filename}")
                
            elif choice == '2':
                # 批量分析
                addresses = []
                print("\n请输入合约地址（每行一个，输入空行结束）:")
                while True:
                    addr = input().strip()
                    if not addr:
                        break
                    addresses.append(addr)
                
                if not addresses:
                    print("未输入任何地址！")
                    continue
                
                print(f"\n开始分析 {len(addresses)} 个合约...")
                for addr in addresses:
                    print(f"\n分析合约: {addr}")
                    report = analyzer.generate_report(addr)
                    print("\n" + report)
                    filename = save_report(report, addr)
                    print(f"报告已保存到文件: {filename}")
            
            elif choice == '3':
                # 生成交易历史报告
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在分析交易历史...")
                filename = analyzer.save_transaction_report(contract_address)
                print(f"\n交易分析报告已保存到: {filename}")
            
            elif choice == '4':
                # 管理RPC节点
                manage_rpc_nodes(analyzer)
            
            elif choice == '5':
                # 管理API密钥
                manage_api_keys(analyzer)
            
            input("\n按回车键继续...")
            
        except Exception as e:
            print(f"\n操作过程中出现错误: {str(e)}")
            input("\n按回车键继续...")

if __name__ == "__main__":
    try:
        # 首先检查并设置虚拟环境
        check_and_setup_venv()
        
        # 添加自动依赖安装（取消注释并修改以下代码）
        print("正在自动安装程序依赖...")
        check_and_install_dependencies()
        
        # 检查命令行参数
        if len(sys.argv) > 1:
            # 命令行模式
            args = parse_args()
            if args.get('address'):
                analyzer = ContractAnalyzer()
                report = analyzer.generate_report(args['address'])
                if args.get('output'):
                    with open(args['output'], 'w', encoding='utf-8') as f:
                        f.write(report)
                    print(f"报告已保存到: {args['output']}")
                else:
                    print(report)
        else:
            # 交互式菜单模式
            main()
    except KeyboardInterrupt:
        print("\n\n程序已被用户中断。")
    except Exception as e:
        print(f"\n程序发生错误: {str(e)}")
