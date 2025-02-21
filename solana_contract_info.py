import subprocess
import sys
import platform
from importlib.metadata import distributions
import base64
import json
from datetime import datetime
from typing import Optional, Dict, Any
import requests
from pathlib import Path

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
        'requests': 'requests'
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
        if package.replace('-', '_') not in installed_packages:
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

class TokenPlatformAnalyzer:
    """代币平台分析器"""
    
    # 已知发币平台的特征
    KNOWN_PLATFORMS = {
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
        
        # 获取合约数据和交互信息
        contract_code = str(contract_data.get('源代码', {}))
        creator = contract_data.get('程序所有者', '')
        recent_txs = contract_data.get('最近交易', [])
        
        # 分析每个已知平台
        for platform_name, platform_info in TokenPlatformAnalyzer.KNOWN_PLATFORMS.items():
            confidence = 0
            reasons = []
            
            # 检查创建者地址
            if creator == platform_info['creator']:
                confidence += 0.6
                reasons.append("创建者地址匹配")
            
            # 检查代码模式
            for pattern in platform_info['patterns']:
                if pattern.lower() in contract_code.lower():
                    confidence += 0.2
                    reasons.append(f"发现平台特征: {pattern}")
            
            # 分析交易指令模式
            for tx in recent_txs:
                for pattern in platform_info['instruction_patterns']:
                    if pattern.lower() in str(tx).lower():
                        confidence += 0.1
                        reasons.append(f"交易包含特征指令: {pattern}")
            
            if confidence > 0:
                results.append({
                    "platform": platform_name,
                    "confidence": min(confidence, 1.0),  # 确保置信度不超过1
                    "reasons": list(set(reasons))  # 去重
                })
        
        return sorted(results, key=lambda x: x['confidence'], reverse=True)

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
    def analyze_security_score(vulnerabilities: dict) -> float:
        """计算合约安全评分"""
        score = 100.0
        
        # 根据漏洞等级扣分
        risk_weights = {
            "high_risk": 20.0,
            "medium_risk": 10.0,
            "low_risk": 5.0
        }
        
        for risk_level, weight in risk_weights.items():
            score -= len(vulnerabilities[risk_level]) * weight
        
        # 确保分数在0-100之间
        return max(0.0, min(100.0, score))

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
    if info.get('安全评分', 100) < 60:
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
            # Solana Foundation
            "https://api.mainnet-beta.solana.com",
            # dRPC
            "https://solana.drpc.org/",
            # GetBlock
            "https://go.getblock.io/4136d34f90a6488b84214ae26f0ed5f4",
            # Allnodes
            "https://solana-rpc.publicnode.com",
            # BlockEden.xyz
            "https://api.blockeden.xyz/solana/67nCBdZQSH9z3YqDDjdm",
            # LeoRPC
            "https://solana.leorpc.com/?api_key=FREE",
            # OMNIA
            "https://endpoints.omniatech.io/v1/sol/mainnet/public",
            # OnFinality
            "https://solana.api.onfinality.io/public",
            # 其他备用节点
            "https://solana-api.projectserum.com",
            "https://rpc.ankr.com/solana",
            "https://solana-mainnet.rpc.extrnode.com",
            "https://solana.public-rpc.com",
            "https://mainnet.rpcpool.com",
            "https://free.rpcpool.com",
        ]
        self.client = None
        self.connect_to_best_rpc()
        
    def connect_to_best_rpc(self):
        """连接到响应最快的RPC节点"""
        print("\n正在尝试连接RPC节点...")
        
        # 根据系统设置不同超时
        os_type = detect_os()
        timeout = 15 if os_type == 'windows' else 10
        
        # 更新后的RPC节点列表
        self.rpc_endpoints = [
            "https://api.mainnet-beta.solana.com",
            "https://rpc.ankr.com/solana",
            "https://solana-api.projectserum.com",
            "https://solana.chainstacklabs.com",
            "https://solana-mainnet.rpc.extrnode.com"
        ]
        
        for endpoint in self.rpc_endpoints:
            try:
                print(f"尝试连接: {endpoint}")
                temp_client = Client(endpoint, timeout=timeout)
                
                # Windows系统禁用代理
                if os_type == 'windows':
                    temp_client._client.proxies = {}  # type: ignore
                
                # 测试连接
                try:
                    slot = temp_client.get_slot()
                    print(f"✅ 连接成功! 当前slot: {slot}")
                    self.client = temp_client
                    return
                except Exception as e:
                    print(f"❌ 连接测试失败: {str(e)}")
                    continue
                
            except Exception as e:
                print(f"❌ 初始化失败: {str(e)}")
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
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
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
                try:
                    token_accounts = self.client.get_token_accounts_by_owner(
                        pubkey,
                        {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
                    ).value
                except:
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
                security_score = VulnerabilityAnalyzer.analyze_security_score(vulnerabilities)
                
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
                        self.connect_to_best_rpc()  # 重新连接RPC
                    except:
                        continue
                else:
                    return {"error": f"分析出错 (已重试{max_retries}次): {str(e)}"}

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
            f"📅 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
        if "发币平台分析" in info and info["发币平台分析"]:
            report.append("\n🏢 发币平台分析:")
            for platform in info["发币平台分析"]:
                report.extend([
                    f"\n可能的平台: {platform['platform']}",
                    f"置信度: {platform['confidence']*100:.1f}%",
                    "原因:"
                ])
                for reason in platform['reasons']:
                    report.append(f"  ✓ {reason}")
        
        # 添加关联代币账户信息
        if info.get("关联代币账户"):
            report.append("\n💳 关联代币账户:")
            for account in info["关联代币账户"]:
                report.append(f"- {account['地址']}")
        
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
                info['字节码']
            ])
        else:
            report.append("❌ 未能获取合约代码")
        
        # 添加交易记录
        report.append("\n📜 最近交易记录:")
        for tx in info['最近交易']:
            report.extend([
                f"- 签名: {tx['签名']}",
                f"  ⏰ 时间: {tx['时间']}",
                f"  状态: {'✅ 成功' if tx['状态'] == '成功' else '❌ 失败'}"
            ])
        
        # 添加安全分析
        report.extend([
            "\n🛡️ 安全分析:",
            f"安全评分: {info['安全评分']:.1f}/100.0",
            
            f"\n{get_risk_level_icon('high_risk')} 高风险漏洞:"
        ])
        
        for vuln in info['漏洞分析']['high_risk']:
            report.extend([
                f"- {vuln['name']}",
                f"  描述: {vuln['description']}",
                f"  发现特征: {', '.join(vuln['matched_patterns'])}"
            ])
        
        report.append(f"\n{get_risk_level_icon('medium_risk')} 中风险漏洞:")
        for vuln in info['漏洞分析']['medium_risk']:
            report.extend([
                f"- {vuln['name']}",
                f"  描述: {vuln['description']}",
                f"  发现特征: {', '.join(vuln['matched_patterns'])}"
            ])
        
        report.append(f"\n{get_risk_level_icon('low_risk')} 低风险漏洞:")
        for vuln in info['漏洞分析']['low_risk']:
            report.extend([
                f"- {vuln['name']}",
                f"  描述: {vuln['description']}",
                f"  发现特征: {', '.join(vuln['matched_patterns'])}"
            ])
        
        report.append("\n⚡ 关键函数:")
        for func in info['漏洞分析']['critical_functions']:
            report.append(f"- {func['function']} ({func['pattern']})")
        
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
            token_holders = self.client.get_token_largest_accounts(pubkey).value
            
            # 获取代币最近交易
            recent_txs = self.client.get_signatures_for_address(
                pubkey,
                limit=10
            ).value
            
            return {
                "地址": str(pubkey),
                "持有者": [
                    {
                        "地址": str(holder.address),
                        "数量": holder.amount,
                        "是否冻结": holder.frozen
                    } for holder in token_holders
                ],
                "最近交易": [
                    {
                        "签名": tx.signature,
                        "时间": datetime.fromtimestamp(tx.block_time).strftime("%Y-%m-%d %H:%M:%S") if tx.block_time else "未知",
                        "状态": "成功" if not tx.err else "失败"
                    } for tx in recent_txs
                ]
            }
        except Exception as e:
            return {"error": f"获取代币信息失败: {str(e)}"}

    def analyze_token_relationships(self, contract_address: str) -> dict:
        """分析代币关系网络"""
        try:
            # 获取所有关联代币账户
            token_accounts = self.client.get_token_accounts_by_owner(
                Pubkey.from_string(contract_address),
                {"programId": Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")}
            ).value
            
            relationships = []
            for account in token_accounts:
                token_info = self.get_token_info(str(account.pubkey))
                if "error" not in token_info:
                    # 分析交易模式
                    tx_pattern = self.analyze_transaction_pattern(token_info["最近交易"])
                    
                    relationships.append({
                        "代币地址": str(account.pubkey),
                        "持有者数量": len(token_info["持有者"]),
                        "交易模式": tx_pattern,
                        "详细信息": token_info
                    })
            
            return relationships
            
        except Exception as e:
            return {"error": f"分析代币关系失败: {str(e)}"}

    def analyze_transaction_pattern(self, transactions: list) -> dict:
        """分析交易模式"""
        return {
            "交易频率": len(transactions),
            "成功率": sum(1 for tx in transactions if tx["状态"] == "成功") / len(transactions) if transactions else 0,
            "最近活动": transactions[0]["时间"] if transactions else "无"
        }

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
3. 仅分析安全漏洞
4. 仅分析发币平台
5. 查看合约交易历史
6. 导出分析报告
7. 追踪关联代币 [新]
0. 退出程序
=====================""")

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
            choice = input("\n请选择功能 (0-7): ").strip()
            
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
                # 仅分析安全漏洞
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在分析合约安全性...")
                analyzer = ContractAnalyzer()
                info = analyzer.get_program_info(contract_address)
                
                if "error" in info:
                    print(f"错误: {info['error']}")
                    continue
                
                print(f"\n安全评分: {info['安全评分']:.1f}/100.0")
                
                print("\n高风险漏洞:")
                for vuln in info['漏洞分析']['high_risk']:
                    print(f"- {vuln['name']}")
                    print(f"  描述: {vuln['description']}")
                    print(f"  发现特征: {', '.join(vuln['matched_patterns'])}")
                
                print("\n中风险漏洞:")
                for vuln in info['漏洞分析']['medium_risk']:
                    print(f"- {vuln['name']}")
                    print(f"  描述: {vuln['description']}")
                    print(f"  发现特征: {', '.join(vuln['matched_patterns'])}")
                
                print("\n低风险漏洞:")
                for vuln in info['漏洞分析']['low_risk']:
                    print(f"- {vuln['name']}")
                    print(f"  描述: {vuln['description']}")
                    print(f"  发现特征: {', '.join(vuln['matched_patterns'])}")
                
            elif choice == '4':
                # 仅分析发币平台
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在分析发币平台...")
                analyzer = ContractAnalyzer()
                info = analyzer.get_program_info(contract_address)
                
                if "error" in info:
                    print(f"错误: {info['error']}")
                    continue
                
                if "发币平台分析" in info and info["发币平台分析"]:
                    for platform in info["发币平台分析"]:
                        print(f"\n可能的平台: {platform['platform']}")
                        print(f"置信度: {platform['confidence']*100:.1f}%")
                        print("原因:")
                        for reason in platform['reasons']:
                            print(f"  - {reason}")
                else:
                    print("\n未识别出具体的发币平台")
                
            elif choice == '5':
                # 查看合约交易历史
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在获取交易历史...")
                analyzer = ContractAnalyzer()
                info = analyzer.get_program_info(contract_address)
                
                if "error" in info:
                    print(f"错误: {info['error']}")
                    continue
                
                print(f"\n最近 {len(info['最近交易'])} 笔交易:")
                for tx in info['最近交易']:
                    print(f"\n签名: {tx['签名']}")
                    print(f"时间: {tx['时间']}")
                    print(f"状态: {tx['状态']}")
                
            elif choice == '6':
                # 导出分析报告
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                output_file = input("请输入报告文件名 (默认为自动生成): ").strip()
                
                print("\n正在生成报告...")
                analyzer = ContractAnalyzer()
                report = analyzer.generate_report(contract_address)
                
                if output_file:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(report)
                    print(f"\n报告已保存到: {output_file}")
                else:
                    filename = save_report(report, contract_address)
                    print(f"\n报告已保存到: {filename}")
            
            elif choice == '7':
                # 追踪关联代币
                contract_address = input("\n请输入要分析的合约地址: ").strip()
                if not contract_address:
                    print("地址不能为空！")
                    continue
                
                print("\n正在分析代币关系...")
                analyzer = ContractAnalyzer()
                relationships = analyzer.analyze_token_relationships(contract_address)
                
                if isinstance(relationships, dict) and "error" in relationships:
                    print(f"错误: {relationships['error']}")
                    continue
                
                print("\n=== 代币关系分析报告 ===")
                print(f"发现 {len(relationships)} 个关联代币\n")
                
                for idx, rel in enumerate(relationships, 1):
                    print(f"代币 {idx}:")
                    print(f"地址: {rel['代币地址']}")
                    print(f"持有者数量: {rel['持有者数量']}")
                    print("交易模式:")
                    print(f"  - 交易频率: {rel['交易模式']['交易频率']} 次")
                    print(f"  - 交易成功率: {rel['交易模式']['成功率']*100:.1f}%")
                    print(f"  - 最近活动: {rel['交易模式']['最近活动']}")
                    
                    print("\n主要持有者:")
                    for holder in rel['详细信息']['持有者'][:5]:  # 显示前5个最大持有者
                        print(f"  - 地址: {holder['地址']}")
                        print(f"    数量: {holder['数量']}")
                        print(f"    状态: {'🔒 已冻结' if holder['是否冻结'] else '✅ 正常'}")
                    print()
                
                # 保存分析结果
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"token_analysis_{contract_address[:8]}_{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(relationships, f, indent=2, ensure_ascii=False)
                print(f"\n详细分析结果已保存到: {filename}")
            
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
