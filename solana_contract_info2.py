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
import grpc
from concurrent import futures
from grpc_tools import protoc
import tempfile

def detect_os() -> str:
    """检测操作系统类型"""
    system = platform.system().lower()
    if 'windows' in system:
        return 'windows'
    elif 'linux' in system:
        return 'linux'
    else:
        return 'other'

def check_and_install_dependencies():
    """检查并安装所需的依赖库"""
    required_packages = {
        'solders': 'solders',
        'solana': 'solana',
        'requests': 'requests',
        'grpcio': 'grpcio',
        'grpcio-tools': 'grpcio-tools',
        'protobuf': 'protobuf'  # 添加protobuf支持
    }
    
    def install_package(package_name):
        print(f"正在安装 {package_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_name],
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
            print(f"{package_name} 安装成功！")
            return True
        except Exception as e:
            print(f"{package_name} 安装失败: {str(e)}")
            return False

    installed_packages = {dist.metadata['Name'] for dist in distributions()}
    
    all_installed = True
    for package, pip_name in required_packages.items():
        package = package.replace('-', '_')  # 处理包名中的横线
        if package not in installed_packages:
            print(f"缺少依赖库: {package}")
            if not install_package(pip_name):
                all_installed = False
    
    if not all_installed:
        print("\n某些依赖库安装失败。")
        print("请手动运行以下命令安装依赖：")
        print(f"python -m pip install --upgrade {' '.join(required_packages.values())}")
        sys.exit(1)
    else:
        print("\n所有依赖库已准备就绪！")

# 在导入其他库之前先检查依赖
print("检查程序依赖...")
check_and_install_dependencies()

from solders.pubkey import Pubkey
from solana.rpc.api import Client
from solana.rpc.commitment import Commitment

# 内嵌Proto定义
PROTO_CONTENT = """
syntax = "proto3";

package solana.v1;

service SolanaService {
    rpc GetAccountInfo(AccountRequest) returns (AccountResponse) {}
    rpc GetTransactions(TransactionRequest) returns (stream TransactionResponse) {}
}

message AccountRequest {
    string address = 1;
}

message AccountResponse {
    string owner = 1;
    bytes data = 2;
}

message TransactionRequest {
    string address = 1;
    uint32 limit = 2;
}

message TransactionResponse {
    string signature = 1;
    int64 block_time = 2;
    repeated Instruction instructions = 3;
}

message Instruction {
    string program_id = 1;
    repeated string accounts = 2;
    bytes data = 3;
}
"""

def setup_grpc():
    """动态生成GRPC代码"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proto_path = Path(tmp_dir) / "solana.proto"
        proto_path.write_text(PROTO_CONTENT)
        
        protoc.main([
            'grpc_tools.protoc',
            f'-I{tmp_dir}',
            f'--python_out={tmp_dir}',
            f'--grpc_python_out={tmp_dir}',
            str(proto_path)
        ])
        
        sys.path.insert(0, tmp_dir)
        global solana_pb2, solana_pb2_grpc
        import solana_pb2 as pb2
        import solana_pb2_grpc as pb2_grpc
    return pb2, pb2_grpc

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

def generate_proto_file():
    """生成 proto 文件并编译"""
    import os
    import sys
    from pathlib import Path
    
    proto_dir = Path(__file__).parent / "generated"
    proto_dir.mkdir(exist_ok=True)
    
    proto_content = '''
    syntax = "proto3";

package solana.rpc.v1;

service SolanaService {
    rpc GetSlot (GetSlotRequest) returns (GetSlotResponse);
    rpc GetTransaction (GetTransactionRequest) returns (GetTransactionResponse);
    rpc GetSignaturesForAddress (GetSignaturesForAddressRequest) returns (GetSignaturesForAddressResponse);
}

message GetSlotRequest {
    string commitment = 1;
}

message GetSlotResponse {
    uint64 slot = 1;
}

message GetTransactionRequest {
    string signature = 1;
    string encoding = 2;
    string commitment = 3;
    uint32 max_supported_transaction_version = 4;
}

message GetTransactionResponse {
    Transaction transaction = 1;
}

message GetSignaturesForAddressRequest {
    string account = 1;
    uint32 limit = 2;
    string commitment = 3;
}

message GetSignaturesForAddressResponse {
    repeated SignatureInfo signatures = 1;
}

message Transaction {
    string signature = 1;
    uint64 slot = 2;
    int64 block_time = 3;
    TransactionMeta meta = 4;
    Message message = 5;
}

message TransactionMeta {
    string err = 1;
    uint64 fee = 2;
    repeated string log_messages = 3;
    repeated TokenBalance pre_token_balances = 4;
    repeated TokenBalance post_token_balances = 5;
    repeated uint64 pre_balances = 6;
    repeated uint64 post_balances = 7;
}

message Message {
    repeated string account_keys = 1;
    repeated Instruction instructions = 2;
}

message Instruction {
    uint32 program_id_index = 1;
    repeated uint32 accounts = 2;
    bytes data = 3;
}

message TokenBalance {
    uint32 account_index = 1;
    string mint = 2;
    TokenAmount ui_token_amount = 3;
}

message TokenAmount {
    string amount = 1;
    uint32 decimals = 2;
    string ui_amount = 3;
}

message SignatureInfo {
    string signature = 1;
    uint64 slot = 2;
    int64 block_time = 3;
    string err = 4;
    string memo = 5;
    string confirmation_status = 6;
}
'''
    
    proto_path = proto_dir / "solana_rpc.proto"
    with open(proto_path, "w") as f:
        f.write(proto_content)
    
    try:
        from grpc_tools import protoc
        
        protoc.main([
            'grpc_tools.protoc',
            f'-I{proto_dir}',
            f'--python_out={proto_dir}',
            f'--grpc_python_out={proto_dir}',
            str(proto_path)
        ])
        
        # 将生成目录添加到Python路径
        if str(proto_dir) not in sys.path:
            sys.path.insert(0, str(proto_dir))
        
        return True
        
    except Exception as e:
        print(f"生成proto文件失败，请确保已安装依赖: pip install grpcio-tools")
        print(f"错误详情: {str(e)}")
        return False

class ContractAnalyzer:
    def __init__(self):
        self.pb2, self.pb2_grpc = setup_grpc()
        self.channel = grpc.secure_channel(
            "solana-yellowstone-grpc.publicnode.com:443",
            grpc.ssl_channel_credentials(),
            options=[
                ('grpc.ssl_target_name_override', 'solana-yellowstone-grpc.publicnode.com'),
                ('grpc.max_receive_message_length', 100 * 1024 * 1024)
            ]
        )
        self.stub = self.pb2_grpc.SolanaServiceStub(self.channel)
        
        # 保留原有分析功能
        self.token_analyzer = TokenPlatformAnalyzer()
        self.vuln_analyzer = VulnerabilityAnalyzer()

    def get_all_transactions(self, address: str, limit=1000):
        """GRPC获取交易数据"""
        try:
            response = self.stub.GetTransactions(
                self.pb2.TransactionRequest(address=address, limit=limit)
            )
            return [self._parse_tx(tx) for tx in response]
        except grpc.RpcError as e:
            print(f"GRPC错误: {e.code().name}")
            return []

    def _parse_tx(self, tx):
        """解析交易数据结构（保持原有解析逻辑）"""
        return {
            "签名": tx.signature,
            "时间": datetime.fromtimestamp(tx.block_time),
            "指令": [{
                "程序": ins.program_id,
                "账户": ins.accounts,
                "数据": base64.b64encode(ins.data).decode()
            } for ins in tx.instructions]
        }

    def get_transaction_details(self, signature: str) -> dict:
        """使用 GRPC 获取交易详情"""
        try:
            from solana_rpc_pb2 import GetTransactionRequest
            
            request = GetTransactionRequest(
                signature=signature,
                encoding="jsonParsed",
                commitment="confirmed",
                max_supported_transaction_version=0
            )
            
            response = self.grpc_client.GetTransaction(request)
            
            if not response.transaction:
                return {}
            
            # 解析交易数据
            tx = response.transaction
            return {
                "签名": signature,
                "状态": "成功" if not tx.meta.err else "失败",
                "时间": datetime.fromtimestamp(tx.block_time).isoformat(),
                "槽位": tx.slot,
                "费用": tx.meta.fee / 1_000_000_000,
                "指令": self._parse_instructions(tx),
                "代币转账": self._parse_token_transfers(tx),
                "SOL转账": self._parse_sol_transfers(tx),
                "日志": tx.meta.log_messages
            }
            
        except Exception as e:
            print(f"获取交易详情失败: {str(e)}")
            return {}

    def _parse_instructions(self, tx):
        """解析交易指令"""
        instructions = []
        for inst in tx.transaction.message.instructions:
            program_id = tx.transaction.message.account_keys[inst.program_id_index]
            accounts = [tx.transaction.message.account_keys[idx] for idx in inst.accounts]
            
            instruction_data = {
                "程序": program_id,
                "账户": accounts,
                "数据": base64.b64encode(inst.data).decode() if inst.data else None,
                "类型": self._identify_program_type(program_id)
            }
            instructions.append(instruction_data)
        return instructions

    def _identify_program_type(self, program_id):
        """识别程序类型"""
        program_types = {
            "11111111111111111111111111111111": "系统程序",
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "代币程序",
            "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter聚合交易"
        }
        return program_types.get(program_id, "其他程序")

    def _parse_token_transfers(self, tx):
        """解析代币转账"""
        transfers = []
        pre_balances = {(b.account_index, b.mint): b.ui_token_amount.amount 
                      for b in tx.meta.pre_token_balances}
        post_balances = {(b.account_index, b.mint): b.ui_token_amount.amount 
                       for b in tx.meta.post_token_balances}
        
        for key in set(pre_balances.keys()) | set(post_balances.keys()):
            pre = pre_balances.get(key, 0)
            post = post_balances.get(key, 0)
            if pre != post:
                transfers.append({
                    "代币": key[1],
                    "账户": tx.transaction.message.account_keys[key[0]],
                    "变化量": post - pre
                })
        return transfers

    def _parse_sol_transfers(self, tx):
        """解析SOL转账"""
        transfers = []
        for i, (pre, post) in enumerate(zip(tx.meta.pre_balances, tx.meta.post_balances)):
            if pre != post:
                transfers.append({
                    "账户": tx.transaction.message.account_keys[i],
                    "变化量": (post - pre) / 1_000_000_000
                })
        return transfers

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
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not self.client:
                    self.connect_to_yellowstone()
                
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
                try:
                    token_accounts = self.client.get_token_accounts_by_owner(
                        pubkey,
                        {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
                    )
                except Exception as e:
                    print(f"获取代币账户时出错: {str(e)}")
                    token_accounts = []
                
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
                            "地址": str(account.pubkey),
                            "数据": base64.b64encode(account.account.data).decode('utf-8')
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
                retry_count += 1
                if retry_count < max_retries:
                    print(f"\n连接失败，正在进行第 {retry_count + 1} 次重试...")
                    try:
                        self.connect_to_yellowstone()  # 重新连接RPC
                    except:
                        continue
                else:
                    return {"error": f"分析出错 (已重试{max_retries}次): {str(e)}"}

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
        """生成详细分析报告"""
        start_time = datetime.now()
        info = self.get_program_info(contract_address)
        analysis_time = (datetime.now() - start_time).total_seconds()
        
        if "error" in info:
            return f"错误: {info['error']}"
        
        # 获取统计信息
        stats = get_stats(info)
        
        report = [
            "=" * 50,
            "🔍 Solana 合约分析报告",
            "=" * 50,
            f"📅 生成时间: {(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)",
            f"⏱️ 分析耗时: {analysis_time:.2f}秒",
            
            "\n📋 基本信息:",
            f"📍 合约地址: {info['合约地址']}",
            f"👤 程序所有者: {info['程序所有者']}",
            f"💰 账户余额: {info['账户余额']} SOL",
            f"⚙️ 是否可执行: {'是' if info['是否可执行'] else '否'}",
            f"📦 数据大小: {info['数据大小']} 字节",
            
            "\n📊 统计信息:",
            f"总交易数: {stats['交易总数']}",
            f"漏洞总数: {sum(stats.values())}",
            "漏洞分布:",
            f"  {get_risk_level_icon('high_risk')} 高风险: {stats['高风险漏洞数']}",
            f"  {get_risk_level_icon('medium_risk')} 中风险: {stats['中风险漏洞数']}",
            f"  {get_risk_level_icon('low_risk')} 低风险: {stats['低风险漏洞数']}"
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

    def get_token_info(self, token_address: str) -> dict:
        """获取代币详细信息"""
        try:
            pubkey = Pubkey.from_string(token_address)
            
            # 获取代币信息
            token_info = self.client.get_account_info(pubkey)
            if not token_info.value:
                return {"error": "未找到代币账户"}
            
            # 获取代币持有者
            token_holders = []
            try:
                holders_info = self.client.get_token_largest_accounts(pubkey)
                if holders_info.value:
                    token_holders = [
                        {
                            "地址": str(holder.address),
                            "数量": holder.amount,
                            "是否冻结": holder.frozen
                        } for holder in holders_info.value
                    ]
            except Exception as e:
                print(f"获取持有者信息失败: {str(e)}")
            
            # 获取代币最近交易
            recent_txs = []
            try:
                tx_info = self.client.get_signatures_for_address(pubkey, limit=10)
                if tx_info.value:
                    recent_txs = [
                        {
                            "签名": tx.signature,
                            "时间": datetime.fromtimestamp(tx.block_time).strftime("%Y-%m-%d %H:%M:%S") if tx.block_time else "未知",
                            "状态": "成功" if not tx.err else "失败"
                        } for tx in tx_info.value
                    ]
            except Exception as e:
                print(f"获取交易历史失败: {str(e)}")
            
            return {
                "地址": str(pubkey),
                "持有者": token_holders,
                "最近交易": recent_txs,
                "数据大小": len(token_info.value.data) if token_info.value.data else 0,
                "所有者": str(token_info.value.owner) if token_info else "未知"
            }
            
        except Exception as e:
            return {"error": f"获取代币信息失败: {str(e)}"}

    def analyze_token_relationships(self, contract_address: str) -> dict:
        try:
            print("开始分析代币关系...")
            pubkey = Pubkey.from_string(contract_address)
            
            # 首先获取合约基本信息
            contract_info = self.get_program_info(contract_address)
            if "error" in contract_info:
                return {"error": f"获取合约信息失败: {contract_info['error']}"}
            
            relationships = {
                "合约信息": {
                    "地址": contract_address,
                    "创建者": contract_info.get('程序所有者'),
                    "类型": "主合约"
                },
                "关联代币": [],
                "关联合约": [],
                "交互地址": [],
                "风险关联": []
            }

            # 1. 修改交易解析逻辑
            try:
                recent_txs = contract_info.get('最近交易', [])
                interacted_addresses = set()
                
                for tx in recent_txs:
                    try:
                        # 修改交易获取方式
                        tx_info = self.client.get_transaction(
                            tx['签名'],
                            commitment=Commitment("confirmed"),
                            max_supported_transaction_version=0
                        )
                        if tx_info.value:
                            # 使用更健壮的账户提取方式
                            transaction_json = tx_info.value.to_json()
                            account_keys = transaction_json.get('result', {}).get('transaction', {}).get('message', {}).get('accountKeys', [])
                            
                            for account in account_keys:
                                addr = str(account)
                                if addr != contract_address:
                                    interacted_addresses.add(addr)
                    except Exception as e:
                        print(f"处理交易 {tx['签名']} 时出错: {str(e)}")
                        continue

            except Exception as e:  # 添加异常处理
                print(f"交易解析失败: {str(e)}")

            # 2. 修改代币账户解析部分
            try:
                token_accounts = self.client.get_token_accounts_by_owner(
                    pubkey,
                    {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
                )
                
                if token_accounts and hasattr(token_accounts, 'value'):
                    for account in token_accounts.value:
                        try:
                            # 使用更安全的字节码解析方式
                            if hasattr(account.account.data, 'parsed'):
                                mint_address = account.account.data.parsed['info']['mint']
                            else:
                                raw_data = base64.b64decode(account.account.data)
                                mint_address = str(Pubkey.from_bytes(raw_data[:32]))
                                
                            token_info = self.get_token_info(mint_address)
                            if "error" not in token_info:
                                relationships["关联代币"].append({
                                    "代币地址": mint_address,
                                    "账户地址": str(account.pubkey),
                                    "持有者数量": len(token_info.get("持有者", [])),
                                    "持有者": token_info.get("持有者", [])[:5],
                                    "最近交易": token_info.get("最近交易", [])[:3]
                                })
                        except Exception as e:
                            print(f"分析代币账户时出错: {str(e)}")
                            continue

            except Exception as e:  # 添加异常处理
                print(f"代币账户解析失败: {str(e)}")

            # 3. 修改相似合约分析部分
            try:
                if contract_info.get('字节码'):
                    # 添加分页和过滤条件
                    similar_programs = self.client.get_program_accounts(
                        Pubkey.from_string("BPFLoaderUpgradeab1e1111111111111111111111111"),
                        filters=[{"dataSize": len(contract_info['字节码'])}]
                    )
                    
                    if similar_programs.value:
                        for program in similar_programs.value:
                            if str(program.pubkey) != contract_address:
                                try:
                                    program_info = self.get_program_info(str(program.pubkey))
                                    if "error" not in program_info and program_info.get('字节码'):
                                        # 直接比较字节码
                                        similarity = self.calculate_bytecode_similarity(
                                            contract_info['字节码'],
                                            program_info['字节码']
                                        )
                                        
                                        if similarity > 0.8:
                                            relationships["关联合约"].append({
                                                "合约地址": str(program.pubkey),
                                                "相似度": similarity,
                                                "创建者": program_info.get('程序所有者'),
                                                "安全评分": program_info.get("安全评分", {}).get("score", 0)
                                            })
                                except Exception as e:
                                    print(f"分析合约 {program.pubkey} 时出错: {str(e)}")
                                    continue
                                    
            except Exception as e:
                print(f"分析相似合约时出错: {str(e)}")

            # 更新统计信息
            relationships["统计信息"] = {
                "关联代币数量": len(relationships["关联代币"]),
                "交互地址数量": len(relationships["交互地址"]),
                "相似合约数量": len(relationships["关联合约"]),
                "风险关联数量": len(relationships["风险关联"]),
                "分析时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            print(f"合约基本信息获取成功: {contract_info.get('程序所有者')}")
            print(f"开始分析最近 {len(contract_info.get('最近交易', []))} 笔交易...")
            # ... 交易分析代码 ...
            
            print(f"交易分析完成，发现 {len(interacted_addresses)} 个交互地址")
            print("开始分析代币账户...")
            # ... 代币分析代码 ...
            
            print("开始分析相似合约...")
            # ... 相似合约分析代码 ...
            
            print("分析完成")
            return relationships
            
        except Exception as e:
            print(f"详细错误: {str(e)}")
            print(f"错误类型: {type(e)}")
            print(f"错误位置: {e.__traceback__.tb_frame.f_code.co_name}")
            return {"error": f"分析代币关系失败: {str(e)}"}

    def calculate_bytecode_similarity(self, bytecode1: str, bytecode2: str) -> float:
        """计算两个字节码的相似度"""
        try:
            if not bytecode1 or not bytecode2:
                return 0.0
            
            # 解码base64
            data1 = base64.b64decode(bytecode1)
            data2 = base64.b64decode(bytecode2)
            
            # 计算最长公共子序列
            len1, len2 = len(data1), len(data2)
            matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
            
            for i in range(1, len1 + 1):
                for j in range(1, len2 + 1):
                    if data1[i-1] == data2[j-1]:
                        matrix[i][j] = matrix[i-1][j-1] + 1
                    else:
                        matrix[i][j] = max(matrix[i-1][j], matrix[i][j-1])
            
            # 计算相似度
            lcs_length = matrix[len1][len2]
            similarity = (2.0 * lcs_length) / (len1 + len2)
            
            return similarity
            
        except Exception as e:
            print(f"计算字节码相似度时出错: {str(e)}")
            return 0.0

    def check_address_risk(self, address: str) -> dict:
        """检查地址风险"""
        try:
            # 1. 检查是否在已知风险地址列表中
            risk_addresses = {
                "高风险": ["已知黑客地址", "诈骗地址"],
                "中风险": ["可疑地址", "高频交易地址"],
                "低风险": []
            }
            
            # 2. 分析地址行为模式
            addr_info = self.get_program_info(address)
            if "error" not in addr_info:
                recent_txs = addr_info.get("最近交易", [])
                
                # 检查交易模式
                if len(recent_txs) >= 3:
                    # 检查高频交易
                    tx_times = [datetime.strptime(tx["时间"], "%Y-%m-%d %H:%M:%S") 
                              for tx in recent_txs]
                    time_diffs = [(tx_times[i] - tx_times[i+1]).total_seconds() 
                                for i in range(len(tx_times)-1)]
                    
                    if any(diff < 1 for diff in time_diffs):
                        return {
                            "风险等级": "中风险",
                            "描述": "发现高频交易行为",
                            "类型": "可疑交易模式"
                        }
                
                # 检查失败率
                failed_txs = sum(1 for tx in recent_txs if tx["状态"] == "失败")
                if failed_txs / len(recent_txs) > 0.5:
                    return {
                        "风险等级": "中风险",
                        "描述": "高交易失败率",
                        "类型": "异常交易模式"
                    }
            
            return {
                "风险等级": "低",
                "描述": "未发现明显风险",
                "类型": "正常地址"
            }
            
        except Exception as e:
            print(f"检查地址风险时出错: {str(e)}")
            return {
                "风险等级": "未知",
                "描述": f"风险分析失败: {str(e)}",
                "类型": "分析错误"
            }

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

    def analyze_arbitrage_opportunity(self, tx_data: dict) -> dict:
        """分析套利机会"""
        result = {
            "可行性": "未知",
            "预期收益": 0,
            "风险等级": "高",
            "建议": []
        }
        
        try:
            # 1. 基础数据（公共RPC可用）
            instructions = tx_data.get("指令详情", [])
            token_transfers = tx_data.get("代币转账", [])
            
            # 2. 价格数据（需要额外API）
            token_prices = {}
            for transfer in token_transfers:
                token_addr = transfer["代币"]
                if token_addr not in token_prices:
                    price = self.get_token_price(token_addr)
                    token_prices[token_addr] = price
            
            # 3. 分析套利路径
            if len(instructions) >= 2:
                dex_path = []
                for inst in instructions:
                    if inst["类型"] in ["Jupiter聚合交易", "Raydium", "Serum"]:
                        dex_path.append(inst["类型"])
                
                if len(dex_path) >= 2:
                    result["可行性"] = "可能"
                    result["建议"].append(
                        f"发现潜在套利路径: {' -> '.join(dex_path)}"
                    )
            
            # 4. 提供建议
            result["建议"].extend([
                "建议使用专业RPC节点获取更详细数据",
                "考虑使用价格预言机获取实时价格",
                "注意MEV保护"
            ])
            
        except Exception as e:
            result["建议"].append(f"分析出错: {str(e)}")
        
        return result

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
3. 查看合约所有交易详情
0. 退出程序
=====================""")

def get_transaction_details(client: Client, signature: str) -> dict:
    """获取单笔交易的详细信息"""
    try:
        # 获取完整交易信息
        tx_info = client.get_transaction(
            signature,
            max_supported_transaction_version=0
        )
        
        if not tx_info.value:
            return {"error": "未找到交易详情"}
            
        tx_data = tx_info.value
        meta = tx_data.meta
        
        # 解析交易费用
        fee = meta.fee / 1_000_000_000 if meta else 0  # 转换为SOL
        
        # 解析交易路由
        instructions = []
        if tx_data.transaction.message.instructions:
            for idx, inst in enumerate(tx_data.transaction.message.instructions):
                program_id = str(tx_data.transaction.message.account_keys[inst.program_id_index])
                
                # 获取指令中涉及的账户
                accounts = [
                    str(tx_data.transaction.message.account_keys[acc_idx])
                    for acc_idx in inst.accounts
                ]
                
                # 尝试解析指令数据
                instruction_data = {
                    "程序": program_id,
                    "账户": accounts,
                    "数据": base64.b64encode(inst.data).decode('utf-8') if inst.data else None
                }
                
                # 识别常见程序
                if program_id == "11111111111111111111111111111111":
                    instruction_data["类型"] = "系统程序"
                elif program_id == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
                    instruction_data["类型"] = "代币程序"
                elif program_id == "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL":
                    instruction_data["类型"] = "关联代币账户程序"
                elif program_id == "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB":
                    instruction_data["类型"] = "Jupiter聚合交易"
                else:
                    instruction_data["类型"] = "未知程序"
                
                instructions.append(instruction_data)
        
        # 解析代币转账
        token_transfers = []
        if meta and meta.post_token_balances and meta.pre_token_balances:
            pre_balances = {
                (b.account_index, b.mint): b.ui_token_amount.amount
                for b in meta.pre_token_balances
            }
            post_balances = {
                (b.account_index, b.mint): b.ui_token_amount.amount
                for b in meta.post_token_balances
            }
            
            # 计算余额变化
            for (acc_idx, mint) in post_balances.keys():
                pre_amt = float(pre_balances.get((acc_idx, mint), 0))
                post_amt = float(post_balances.get((acc_idx, mint), 0))
                if pre_amt != post_amt:
                    token_transfers.append({
                        "代币": mint,
                        "账户": str(tx_data.transaction.message.account_keys[acc_idx]),
                        "变化量": post_amt - pre_amt
                    })
        
        # 解析SOL转账
        sol_transfers = []
        if meta and meta.post_balances and meta.pre_balances:
            for idx, (pre, post) in enumerate(zip(meta.pre_balances, meta.post_balances)):
                if pre != post:
                    sol_transfers.append({
                        "账户": str(tx_data.transaction.message.account_keys[idx]),
                        "变化量": (post - pre) / 1_000_000_000  # 转换为SOL
                    })
        
        return {
            "签名": signature,
            "状态": "成功" if not meta.err else "失败",
            "区块时间": datetime.fromtimestamp(tx_data.block_time).strftime("%Y-%m-%d %H:%M:%S") if tx_data.block_time else "未知",
            "槽位": tx_data.slot,
            "交易费用": fee,
            "指令数量": len(instructions),
            "指令详情": instructions,
            "代币转账": token_transfers,
            "SOL转账": sol_transfers,
            "确认状态": tx_data.meta.err if meta else None,
            "日志": meta.log_messages if meta else []
        }
        
    except Exception as e:
        return {"error": f"获取交易详情失败: {str(e)}"}

def analyze_transaction_pattern(tx_data: dict) -> dict:
    """分析交易模式，识别套利等特殊行为"""
    patterns = {
        "类型": "普通交易",
        "特征": [],
        "风险等级": "低",
        "详细说明": []
    }
    
    try:
        instructions = tx_data.get("指令详情", [])
        token_transfers = tx_data.get("代币转账", [])
        sol_transfers = tx_data.get("SOL转账", [])
        logs = tx_data.get("日志", [])
        
        # 1. 检测 DEX 套利模式
        dex_programs = {
            "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter",
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
            "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin": "Serum",
            "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca"
        }
        
        dex_interactions = []
        for inst in instructions:
            program_id = inst["程序"]
            if program_id in dex_programs:
                dex_interactions.append(dex_programs[program_id])
        
        if len(dex_interactions) >= 2:
            patterns["类型"] = "DEX套利交易"
            patterns["特征"].append("多DEX交互")
            patterns["详细说明"].append(
                f"交易涉及多个DEX: {' -> '.join(dex_interactions)}"
            )
            patterns["风险等级"] = "中"
        
        # 2. 检测闪电贷模式
        if any("flash_loan" in str(log).lower() for log in logs):
            patterns["类型"] = "闪电贷交易"
            patterns["特征"].append("闪电贷")
            patterns["风险等级"] = "高"
            patterns["详细说明"].append("交易包含闪电贷操作")
        
        # 3. 检测高频交易模式
        if len(instructions) > 5:
            patterns["特征"].append("复杂交易")
            patterns["详细说明"].append(f"交易包含 {len(instructions)} 个指令")
        
        # 4. 分析代币流向
        if token_transfers:
            # 检查是否存在代币互换
            tokens_in = set()
            tokens_out = set()
            for transfer in token_transfers:
                if transfer["变化量"] > 0:
                    tokens_in.add(transfer["代币"])
                else:
                    tokens_out.add(transfer["代币"])
            
            if tokens_in and tokens_out:
                patterns["特征"].append("代币互换")
                patterns["详细说明"].append(
                    f"代币互换: {', '.join(tokens_out)} -> {', '.join(tokens_in)}"
                )
        
        # 5. 检测特殊模式
        special_patterns = {
            "sandwich": "三笔连续交易，中间交易被前后包夹",
            "front_running": "在大额交易前抢先交易",
            "wash_trading": "同一地址之间的来回交易"
        }
        
        # 检查是否存在套利特征
        if len(dex_interactions) >= 2 and token_transfers:
            profit_analysis = analyze_profit(token_transfers, sol_transfers)
            if profit_analysis["利润"] > 0:
                patterns["特征"].append("套利获利")
                patterns["详细说明"].append(
                    f"预计获利: {profit_analysis['利润']} SOL\n" +
                    f"套利路径: {profit_analysis['路径']}"
                )
        
        return patterns
        
    except Exception as e:
        patterns["详细说明"].append(f"分析出错: {str(e)}")
        return patterns

def analyze_profit(token_transfers: list, sol_transfers: list) -> dict:
    """分析交易获利情况"""
    result = {
        "利润": 0,
        "路径": "",
        "详情": []
    }
    
    try:
        # 计算SOL净变化
        sol_profit = sum(transfer["变化量"] for transfer in sol_transfers)
        
        # 分析代币变化
        token_changes = {}
        for transfer in token_transfers:
            token = transfer["代币"]
            if token not in token_changes:
                token_changes[token] = 0
            token_changes[token] += transfer["变化量"]
        
        # 构建交易路径
        path = []
        for token, amount in token_changes.items():
            if amount != 0:  # 非零净变化
                path.append(f"{token}({amount:+.4f})")
        
        result["利润"] = sol_profit
        result["路径"] = " -> ".join(path) if path else "直接SOL获利"
        result["详情"] = {
            "SOL变化": sol_profit,
            "代币变化": token_changes
        }
        
    except Exception as e:
        result["详情"].append(f"分析出错: {str(e)}")
    
    return result

def generate_transaction_report(transactions: list, contract_address: str) -> str:
    """生成更详细的交易报告，包含套利分析"""
    report = [
        "=" * 50,
        f"🔍 Solana 合约交易详情报告",
        "=" * 50,
        f"📅 生成时间: {(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)",
        f"📍 合约地址: {contract_address}",
        f"📊 总交易数: {len(transactions)}",
        "\n=== 交易统计 ===",
        f"成功交易: {sum(1 for tx in transactions if tx['状态'] == '成功')}",
        f"失败交易: {sum(1 for tx in transactions if tx['状态'] == '失败')}",
        "\n=== 详细交易记录 ===\n"
    ]
    
    # 添加交易模式分析
    for tx in transactions:
        pattern_analysis = analyze_transaction_pattern(tx)
        report.extend([
            f"签名: {tx['签名']}",
            f"时间: {tx['时间']} (UTC+8)",
            f"状态: {'✅ ' if tx['状态'] == '成功' else '❌ '}{tx['状态']}",
            f"交易费用: {tx.get('交易费用', '未知')} SOL",
            f"交易类型: {pattern_analysis['类型']}",
            f"风险等级: {pattern_analysis['风险等级']}"
        ])
        
        if pattern_analysis['特征']:
            report.append("交易特征:")
            for feature in pattern_analysis['特征']:
                report.append(f"  • {feature}")
        
        if pattern_analysis['详细说明']:
            report.append("详细说明:")
            for detail in pattern_analysis['详细说明']:
                report.append(f"  • {detail}")
        
        # ... 原有的交易详情代码 ...
        
        report.append("-" * 50 + "\n")
    
    # 添加统计分析
    report.extend([
        "\n=== 交易模式统计 ===",
        f"套利交易: {sum(1 for tx in transactions if '套利' in analyze_transaction_pattern(tx)['类型'])}",
        f"闪电贷交易: {sum(1 for tx in transactions if '闪电贷' in analyze_transaction_pattern(tx)['特征'])}",
        f"高频交易: {sum(1 for tx in transactions if '复杂交易' in analyze_transaction_pattern(tx)['特征'])}"
    ])
    
    return "\n".join(report)

def parse_transaction_details(tx_data) -> dict:
    """解析交易详细信息"""
    details = {}
    try:
        # 解析指令
        if hasattr(tx_data.transaction.message, 'instructions'):
            instructions = []
            for inst in tx_data.transaction.message.instructions:
                inst_data = {
                    "程序ID": str(tx_data.transaction.message.account_keys[inst.program_id_index]),
                    "账户": [str(tx_data.transaction.message.account_keys[idx]) for idx in inst.accounts],
                    "数据": base64.b64encode(inst.data).decode('utf-8') if inst.data else None
                }
                instructions.append(inst_data)
            details["指令"] = instructions
        
        # 解析代币转账
        if tx_data.meta and tx_data.meta.post_token_balances:
            token_changes = []
            pre_balances = {(b.account_index, b.mint): b.ui_token_amount.amount 
                          for b in tx_data.meta.pre_token_balances}
            post_balances = {(b.account_index, b.mint): b.ui_token_amount.amount 
                           for b in tx_data.meta.post_token_balances}
            
            for (acc_idx, mint) in post_balances.keys():
                pre = float(pre_balances.get((acc_idx, mint), 0))
                post = float(post_balances[acc_idx, mint])
                if pre != post:
                    token_changes.append({
                        "代币": mint,
                        "账户": str(tx_data.transaction.message.account_keys[acc_idx]),
                        "变化": post - pre
                    })
            details["代币变化"] = token_changes
        
        # 解析SOL转账
        if tx_data.meta and tx_data.meta.pre_balances and tx_data.meta.post_balances:
            sol_changes = []
            for i, (pre, post) in enumerate(zip(tx_data.meta.pre_balances, tx_data.meta.post_balances)):
                if pre != post:
                    sol_changes.append({
                        "账户": str(tx_data.transaction.message.account_keys[i]),
                        "变化": (post - pre) / 1_000_000_000
                    })
            details["SOL变化"] = sol_changes
        
        # 添加日志
        if tx_data.meta and tx_data.meta.log_messages:
            details["日志"] = tx_data.meta.log_messages
            
    except Exception as e:
        details["解析错误"] = str(e)
    
    return details

def main():
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
    
    while True:
        print_menu()
        try:
            choice = input("\n请选择功能 (0-3): ").strip()
            
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
                analyzer = ContractAnalyzer()
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
                analyzer = ContractAnalyzer()
                for addr in addresses:
                    print(f"\n分析合约: {addr}")
                    report = analyzer.generate_report(addr)
                    print("\n" + report)
                    filename = save_report(report, addr)
                    print(f"报告已保存到文件: {filename}")
            
            elif choice == '3':
                # 查看所有交易详情
                contract_address = input("\n请输入要查询的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在获取交易记录...")
                analyzer = ContractAnalyzer()
                # 修改这里：使用analyzer实例调用get_all_transactions
                transactions = analyzer.get_all_transactions(contract_address)
                
                if not transactions:
                    print("未找到交易记录！")
                    continue
                
                # 打印最近的5笔交易
                print(f"\n找到 {len(transactions)} 笔交易")
                print("\n最近5笔交易:")
                for tx in transactions[:5]:
                    print(f"时间: {tx['时间']} | 状态: {'✅' if tx['状态']=='成功' else '❌'} | 签名: {tx['签名'][:32]}...")
                
                # 生成完整报告并保存
                report = generate_transaction_report(transactions, contract_address)
                filename = save_report(report, contract_address, format='transactions.txt')
                print(f"\n完整交易记录已保存到文件: {filename}")
            
            input("\n按回车键继续...")
            
        except Exception as e:
            print(f"\n操作过程中出现错误: {str(e)}")
            input("\n按回车键继续...")

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            # 命令行模式
            args = parse_args()
            if 'address' in args:
                analyzer = ContractAnalyzer()
                report = analyzer.generate_report(args['address'])
                if 'output' in args:
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
