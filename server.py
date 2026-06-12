"""
ConflictCompass - AI 辅助 HR 沟通话术生成与合规检查工具
Flask 后端服务
"""
import os
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from anthropic import Anthropic

# ============================================================
# 应用初始化
# ============================================================

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

DB_PATH = Path(__file__).parent / "conflict_compass.db"
DATA_DIR = Path(__file__).parent / "data"

# Anthropic 客户端（延迟初始化）
_anthropic_client = None


def _find_api_key():
    """从多个来源查找 API Key"""
    # 1. 当前进程环境变量
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    # 2. Windows 注册表（用户变量）
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg:
            key, _ = winreg.QueryValueEx(reg, "ANTHROPIC_API_KEY")
            if key and key.strip():
                return key.strip()
    except Exception:
        pass
    return ""


def get_ai_client():
    """获取 Anthropic 客户端（延迟初始化，支持多来源查找 API Key）"""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = _find_api_key()
        if not api_key:
            raise ValueError(
                "未找到 ANTHROPIC_API_KEY。请在 PowerShell 中执行：`setx ANTHROPIC_API_KEY \"你的Key\"`，"
                "然后重新打开窗口运行 start.bat。"
            )
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


# ============================================================
# 数据库
# ============================================================

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lifecycle_stage TEXT NOT NULL,
            scenario TEXT NOT NULL,
            level TEXT DEFAULT '',
            emotion TEXT DEFAULT '',
            tone TEXT DEFAULT '',
            extra_info TEXT DEFAULT '',
            content TEXT NOT NULL,
            predictions TEXT DEFAULT '[]',
            optimization TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lifecycle_stage TEXT NOT NULL,
            scenario TEXT NOT NULL,
            default_tone TEXT DEFAULT '正式严肃',
            default_notes TEXT DEFAULT '',
            is_preset INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def insert_preset_templates():
    """插入预置场景模板（如果不存在）"""
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) as cnt FROM templates WHERE is_preset=1").fetchone()
    if existing["cnt"] > 0:
        conn.close()
        return

    presets = [
        ("入职融入-试用期目标沟通", "入职融入", "试用期目标沟通", "鼓励支持",
         "适用于新员工入职后设定试用期目标和期望的沟通"),
        ("入职融入-转正评估面谈", "入职融入", "转正评估面谈", "正式严肃",
         "适用于试用期结束时的转正评估反馈面谈"),
        ("在岗管理-绩效反馈", "在岗管理", "绩效考核反馈", "温和关切",
         "适用于定期绩效评估后的反馈沟通"),
        ("在岗管理-PIP启动", "在岗管理", "绩效改进计划启动", "坚定但尊重",
         "适用于启动正式绩效改进计划时的严肃沟通"),
        ("纪律与冲突-违纪警告", "纪律与冲突", "违纪警告", "正式严肃",
         "适用于员工违反公司纪律时的正式警告沟通"),
        ("异动与调整-调岗沟通", "异动与调整", "调岗沟通", "温和关切",
         "适用于因业务需要与员工沟通岗位调整"),
        ("离职与善后-离职挽留", "离职与善后", "离职挽留面谈", "温和关切",
         "适用于核心员工提出离职时的挽留沟通"),
        ("离职与善后-裁员通知", "离职与善后", "裁员通知", "坚定但尊重",
         "适用于因业务调整需要与员工沟通裁员安排"),
    ]

    for name, stage, scenario, tone, notes in presets:
        conn.execute(
            "INSERT INTO templates (name, lifecycle_stage, scenario, default_tone, default_notes, is_preset) VALUES (?,?,?,?,?,1)",
            (name, stage, scenario, tone, notes)
        )
    conn.commit()
    conn.close()


# ============================================================
# 配置加载
# ============================================================

def load_json(filename):
    filepath = DATA_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_compliance_rules():
    data = load_json("compliance_rules.json")
    return data.get("categories", []) if data else []


def load_taboo_words():
    data = load_json("taboo_words.json")
    return data.get("words", []) if data else []


# ============================================================
# 禁忌词本地扫描
# ============================================================

def scan_taboo_words(text):
    """扫描文本中的禁忌词，返回命中列表"""
    taboo_words = load_taboo_words()
    hits = []
    for item in taboo_words:
        word = item["word"]
        if word in text:
            # 使用简单的位置标记（实际前端会用更精确的标记方式）
            hits.append({
                "word": word,
                "level": item["level"],
                "category": item.get("category", ""),
                "suggestions": item.get("suggestions", []),
                "context": _extract_context(text, word),
            })
    return hits


def _extract_context(text, word, context_chars=30):
    """提取命中词周围的上下文"""
    idx = text.find(word)
    if idx < 0:
        return ""
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(word) + context_chars)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


# ============================================================
# Prompt 构建
# ============================================================

LIFECYCLE_CONTEXT = {
    "入职融入": "员工刚加入公司，处于试用期或刚转正阶段。沟通重点在于建立信任、明确期望、帮助融入。",
    "在岗管理": "员工处于正常工作期。沟通重点在于客观反馈、设定目标、推动成长。",
    "纪律与冲突": "员工出现违纪行为或卷入冲突。沟通重点在于事实陈述、纪律说明、给出改进路径。",
    "异动与调整": "员工面临岗位、职级或薪酬调整。沟通重点在于原因说明、影响分析、方案展示。",
    "离职与善后": "员工即将或可能离开公司。沟通重点在于尊重理解、法律合规、妥善善后。",
}


def build_generate_prompt(params):
    """构建话术生成的 User Prompt"""
    stage = params.get("lifecycle_stage", "")
    scenario = params.get("scenario", "")
    level = params.get("level", "")
    emotion = params.get("emotion", "")
    tone = params.get("tone", "")
    extra = params.get("extra_info", "")

    context = LIFECYCLE_CONTEXT.get(stage, "")

    prompt = f"""请作为资深 HR 沟通顾问，为以下场景生成专业的沟通话术。

【场景信息】
- 生命周期阶段：{stage}
- 具体场景：{scenario}
- 对方职级：{level}
- 对方当前情绪：{emotion}
- 期望沟通语气：{tone}
- 补充背景：{extra if extra else "无"}

【阶段背景】
{context}

【输出要求】
1. 话术必须严格分为三个部分，每部分以对应标签开头：
   【开场】—— 建立沟通氛围，说明面谈目的（2-3句话）
   【核心】—— 陈述事实、说明原因、探讨方案（核心内容，4-6句话）
   【收尾】—— 总结共识、明确下一步、表达支持（2-3句话）

2. 语言要求：
   - 专业但不生硬，体现尊重和同理心
   - 语气为「{tone}」
   - 避免任何威胁性、歧视性、侮辱性语言
   - 避免使用"你必须""否则""后果自负"等刺激性词汇
   - 对方情绪为「{emotion}」，请在话术中体现对情绪的理解和安抚

3. 输出完话术后，请额外输出一个「对方反应预判」部分：
   【预判回应】
   问题1：[对方可能提出的问题]
   应对1：[建议应对话术]
   问题2：[对方可能提出的问题]
   应对2：[建议应对话术]
   问题3：[对方可能提出的问题]
   应对3：[建议应对话术]

请仅输出话术内容和预判回应，不要添加额外的解释说明。"""
    return prompt


def build_optimize_prompt(params):
    """构建话术优化的 User Prompt"""
    original = params.get("original_script", {})
    direction = params.get("direction", "更专业")
    extra_notes = params.get("extra_notes", "")

    original_text = f"""【开场】{original.get('opening', '')}
【核心】{original.get('core', '')}
【收尾】{original.get('closing', '')}"""

    prompt = f"""请作为资深 HR 沟通顾问，优化以下话术。

【优化方向】{direction}
{"【补充要求】" + extra_notes if extra_notes else ""}

【原话术】
{original_text}

【输出要求】
1. 输出优化后的完整话术，严格保持【开场】【核心】【收尾】标签格式
2. 在话术后输出优化说明：
   【修改说明】
   - 修改点1：xxx
   - 修改点2：xxx
3. 保持专业、合规、尊重员工的沟通原则
4. 避免刺激性词汇和威胁性语言

请仅输出优化后的话术和修改说明，不要添加其他内容。"""
    return prompt


def build_check_prompt(script_text):
    """构建合规检查的 User Prompt"""
    rules = load_compliance_rules()
    rules_text = ""
    for i, cat in enumerate(rules, 1):
        laws = "\n".join([f"    - {lr['law']}：{lr['content'][:200]}" for lr in cat.get("legal_references", [])])
        rules_text += f"""
{i}. {cat['name']}（风险等级：{cat.get('risk_level', 'unknown')}）
   说明：{cat.get('description', '')}
   法律依据：
{laws}
"""

    prompt = f"""请作为劳动法合规专家，严格检查以下 HR 沟通话术是否触碰法律红线。

【待检查话术】
{script_text}

【合规红线清单】
{rules_text}

【输出格式 — 必须严格遵守】
请对以下 {len(rules)} 项逐条输出，每条用三行，格式固定为：
CATEGORY: <红线名称>
VERDICT: <通过/提醒/违规>
REASON: <理由（一句话）>

最后输出 SUMMARY 行：
SUMMARY: 通过X,提醒Y,违规Z

示例格式：
CATEGORY: 歧视性表述
VERDICT: 通过
REASON: 话术中未发现性别、年龄、民族、宗教等方面的歧视性内容
CATEGORY: 威胁恐吓
VERDICT: 违规
REASON: 话术中包含"后果自负"等威胁性表述
SUMMARY: 通过7,提醒1,违规1

请严格按照上述格式输出，不要添加额外说明文字。"""
    return prompt


# ============================================================
# AI 调用封装
# ============================================================

def call_claude(system_prompt, user_prompt, max_tokens=2000):
    """调用 Claude API"""
    client = get_ai_client()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )
    # 从响应中提取纯文本（跳过 thinking block）
    for block in message.content:
        if block.type == "text":
            return block.text
    # 兜底：如果没找到 text block，尝试第一个 block
    return message.content[0].text if hasattr(message.content[0], "text") else str(message.content[0])


# ============================================================
# 响应解析
# ============================================================

def parse_script_response(text):
    """解析 AI 生成的话术，提取【开场】【核心】【收尾】和【预判回应】"""
    result = {
        "opening": "",
        "core": "",
        "closing": "",
        "predictions": []
    }

    # 提取话术部分
    opening_match = re.search(r'【开场】\s*(.*?)(?=【核心】|$)', text, re.DOTALL)
    core_match = re.search(r'【核心】\s*(.*?)(?=【收尾】|$)', text, re.DOTALL)
    closing_match = re.search(r'【收尾】\s*(.*?)(?=【预判回应】|$)', text, re.DOTALL)

    if opening_match:
        result["opening"] = opening_match.group(1).strip()
    if core_match:
        result["core"] = core_match.group(1).strip()
    if closing_match:
        result["closing"] = closing_match.group(1).strip()

    # 提取预判回应
    pred_section = re.search(r'【预判回应】\s*(.*?)$', text, re.DOTALL)
    if pred_section:
        pred_text = pred_section.group(1)
        # 解析每个 问题/应对 对
        qa_pairs = re.findall(r'问题\d+[：:]\s*(.*?)\s*应对\d+[：:]\s*(.*?)(?=问题\d+[：:]|$)', pred_text, re.DOTALL)
        for q, a in qa_pairs:
            result["predictions"].append({
                "question": q.strip(),
                "response": a.strip()
            })
        # 也尝试另一种常见格式（问题后换行再应对）
        if not qa_pairs:
            lines = pred_text.strip().split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                q_match = re.match(r'问题?\d*[：:]\s*(.*)', line)
                if q_match and i + 1 < len(lines):
                    a_match = re.match(r'应对?\d*[：:]\s*(.*)', lines[i + 1].strip())
                    if a_match:
                        result["predictions"].append({
                            "question": q_match.group(1).strip(),
                            "response": a_match.group(1).strip()
                        })
                        i += 2
                        continue
                i += 1

    return result


def parse_check_response(text):
    """解析合规检查结果"""
    results = []
    rules = load_compliance_rules()

    # 按 CATEGORY: 行分割，更稳健的方式
    # 先找到所有 CATEGORY 行的位置
    cat_positions = [m.start() for m in re.finditer(r'^CATEGORY:', text, re.MULTILINE)]
    blocks = []
    for i, pos in enumerate(cat_positions):
        end = cat_positions[i + 1] if i + 1 < len(cat_positions) else len(text)
        blocks.append(text[pos:end])

    # 解析每个块
    parsed = {}
    for block in blocks:
        cat_match = re.search(r'CATEGORY:\s*(.*)', block)
        ver_match = re.search(r'VERDICT:\s*(通过|提醒|违规)', block)
        reason_match = re.search(r'REASON:\s*(.*)', block)
        if cat_match:
            name = cat_match.group(1).strip()
            parsed[name] = {
                "status": ver_match.group(1).strip() if ver_match else "pass",
                "detail": reason_match.group(1).strip() if reason_match else "",
            }

    # 汇总行
    summary_match = re.search(r'SUMMARY:\s*通过(\d+).*?提醒(\d+).*?违规(\d+)', text)

    # 按合规规则顺序组装结果
    for cat in rules:
        name = cat["name"]
        info = parsed.get(name, {"status": "pass", "detail": "（AI 未输出此项，默认通过）"})
        status = info["status"]
        detail = info["detail"]

        legal_refs = []
        if status in ("violation", "warning"):
            for lr in cat.get("legal_references", []):
                legal_refs.append({"law": lr["law"], "content": lr["content"]})

        results.append({
            "category": name,
            "status": status,
            "detail": detail,
            "legal_references": legal_refs,
            "suggestion": _get_suggestion(cat, status),
        })

    total = len(results)
    # 状态映射：AI 返回中文，统一转为英文键
    STATUS_MAP = {"通过": "pass", "提醒": "warning", "违规": "violation"}
    for r in results:
        r["status"] = STATUS_MAP.get(r["status"], r["status"])

    pass_count = sum(1 for r in results if r["status"] == "pass")
    warning_count = sum(1 for r in results if r["status"] == "warning")
    violation_count = sum(1 for r in results if r["status"] == "violation")

    return {
        "results": results,
        "summary": {
            "total": total,
            "pass": pass_count,
            "warning": warning_count,
            "violation": violation_count,
        }
    }


def _get_suggestion(cat, status):
    """根据类别和状态给出建议"""
    if status == "pass":
        return ""
    suggestions = {
        "歧视性表述": "请删除任何涉及性别、年龄、民族、宗教、残疾等特征的差别对待表述。",
        "违法解除劳动合同暗示": "请确保解除劳动合同的理由符合《劳动合同法》第39-41条的法定情形。",
        "强迫辞职/变相胁迫": "请删除任何暗示员工主动辞职的表述，协商解除应基于双方自愿。",
        "威胁性/恐吓性语言": "请删除所有威胁性、恐吓性表述，改用客观事实陈述。",
        "工资克扣威胁": "请删除以扣发工资作为威胁的表述，工资支付应依法依规。",
        "隐私侵犯": "请删除涉及员工个人隐私的公开或暗示性表述。",
        "名誉损害/侮辱性表述": "请删除侮辱、贬低性语言，保持对员工人格尊严的尊重。",
        "法定程序缺失": "请补充说明法定程序要求，如提前通知期限、经济补偿方案等。",
        "竞业限制滥用": "请确认竞业限制人员范围和期限符合《劳动合同法》第23-24条规定。",
    }
    return suggestions.get(cat["name"], "请对照相关法律法规进行修改。")


# ============================================================
# API 路由
# ============================================================

# --- 健康检查 ---

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/ping")
def ping():
    rules = load_json("compliance_rules.json")
    taboo = load_json("taboo_words.json")
    has_api_key = bool(_find_api_key())
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat(),
        "api_key_configured": has_api_key,
        "config": {
            "compliance_rules_loaded": rules is not None,
            "taboo_words_loaded": taboo is not None,
            "rules_count": len(rules.get("categories", [])) if rules else 0,
            "taboo_words_count": len(taboo.get("words", [])) if taboo else 0,
        }
    })


# --- 话术生成 ---

@app.route("/api/generate", methods=["POST"])
def generate_script():
    try:
        params = request.get_json()
        if not params:
            return jsonify({"success": False, "error": "请提供请求参数"}), 400

        required = ["lifecycle_stage", "scenario"]
        for key in required:
            if not params.get(key):
                return jsonify({"success": False, "error": f"缺少必填参数：{key}"}), 400

        # 构建 Prompt 并调用 AI
        user_prompt = build_generate_prompt(params)

        system_prompt = """你是一位资深的 HR 沟通顾问和劳动法专家，拥有20年人力资源管理经验。
你的任务是为 HR 人员生成专业、合规、有温度的沟通话术。
你必须严格遵循输出格式要求，在话术中体现对员工的尊重和同理心。
话术中绝对不能出现威胁、歧视、侮辱性语言。
当涉及裁员、降职等敏感场景时，确保话术合法合规。"""

        ai_response = call_claude(system_prompt, user_prompt, max_tokens=2500)

        # 解析响应
        parsed = parse_script_response(ai_response)

        # 组合完整话术文本用于禁忌词扫描
        full_text = f"【开场】{parsed['opening']}\n【核心】{parsed['core']}\n【收尾】{parsed['closing']}"

        # 禁忌词扫描
        taboo_hits = scan_taboo_words(full_text)

        # 保存到数据库
        conn = get_db()
        cursor = conn.execute(
            """INSERT INTO scripts (lifecycle_stage, scenario, level, emotion, tone, extra_info, content, predictions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                params.get("lifecycle_stage", ""),
                params.get("scenario", ""),
                params.get("level", ""),
                params.get("emotion", ""),
                params.get("tone", ""),
                params.get("extra_info", ""),
                json.dumps({"opening": parsed["opening"], "core": parsed["core"], "closing": parsed["closing"]}, ensure_ascii=False),
                json.dumps(parsed["predictions"], ensure_ascii=False),
            )
        )
        script_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "id": script_id,
            "script": {
                "opening": parsed["opening"],
                "core": parsed["core"],
                "closing": parsed["closing"],
            },
            "predictions": parsed["predictions"],
            "taboo_hits": taboo_hits,
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except Exception as e:
        return jsonify({"success": False, "error": f"生成失败：{str(e)}"}), 500


# --- 话术优化 ---

@app.route("/api/optimize", methods=["POST"])
def optimize_script():
    try:
        params = request.get_json()
        if not params or not params.get("original_script"):
            return jsonify({"success": False, "error": "请提供原话术"}), 400

        user_prompt = build_optimize_prompt(params)

        system_prompt = """你是一位专业的 HR 沟通话术编辑，擅长优化和润色沟通文本。
你的优化原则：
1. 保持原意的基础上提升表达效果
2. 确保语言专业、合规、尊重员工
3. 避免刺激性词汇和威胁性语言
4. 优化方向由用户指定，严格遵守"""

        ai_response = call_claude(system_prompt, user_prompt, max_tokens=2000)

        # 解析优化后的内容
        parsed = parse_script_response(ai_response)

        # 提取修改说明
        changes = ""
        changes_match = re.search(r'【修改说明】\s*(.*?)$', ai_response, re.DOTALL)
        if changes_match:
            changes = changes_match.group(1).strip()

        # 禁忌词扫描
        full_text = f"【开场】{parsed.get('opening', '')}\n【核心】{parsed.get('core', '')}\n【收尾】{parsed.get('closing', '')}"
        taboo_hits = scan_taboo_words(full_text)

        # 如果传了 script_id，更新该记录的优化版本
        script_id = params.get("script_id")
        if script_id:
            conn = get_db()
            conn.execute(
                "UPDATE scripts SET optimization = ? WHERE id = ?",
                (json.dumps({"opening": parsed.get("opening", ""), "core": parsed.get("core", ""), "closing": parsed.get("closing", ""), "changes": changes}, ensure_ascii=False), script_id)
            )
            conn.commit()
            conn.close()

        return jsonify({
            "success": True,
            "optimized_script": {
                "opening": parsed.get("opening", ""),
                "core": parsed.get("core", ""),
                "closing": parsed.get("closing", ""),
            },
            "changes_summary": changes,
            "taboo_hits": taboo_hits,
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except Exception as e:
        return jsonify({"success": False, "error": f"优化失败：{str(e)}"}), 500


# --- 合规检查 ---

@app.route("/api/check", methods=["POST"])
def check_compliance():
    try:
        params = request.get_json()
        script_text = ""
        if params:
            # 支持传入完整文本或结构化对象
            if "text" in params:
                script_text = params["text"]
            elif "script" in params:
                s = params["script"]
                if isinstance(s, dict):
                    script_text = f"【开场】{s.get('opening', '')}\n【核心】{s.get('core', '')}\n【收尾】{s.get('closing', '')}"
                else:
                    script_text = str(s)
            else:
                return jsonify({"success": False, "error": "请提供待检查的话术文本"}), 400

        if not script_text.strip():
            return jsonify({"success": False, "error": "话术文本为空"}), 400

        # AI 合规检查
        user_prompt = build_check_prompt(script_text)

        system_prompt = """你是一位劳动法合规审查专家，精通中国劳动法律法规。
你的任务是严格逐项检查 HR 沟通话术是否触碰法律红线。
对于每个检查项，请给出明确的判断结论：
- "通过"：话术中未发现该类风险
- "提醒"：话术中存在轻微隐患，建议优化
- "违规"：话术明显违反相关法律规定，需立即修改
判断要准确、客观，不夸大也不轻描淡写。"""

        ai_response = call_claude(system_prompt, user_prompt, max_tokens=2500)

        # 解析检查结果
        check_results = parse_check_response(ai_response)

        # 禁忌词扫描
        taboo_hits = scan_taboo_words(script_text)

        return jsonify({
            "success": True,
            **check_results,
            "taboo_words": taboo_hits,
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except Exception as e:
        return jsonify({"success": False, "error": f"检查失败：{str(e)}"}), 500


# --- 历史记录 ---

@app.route("/api/history", methods=["GET"])
def get_history():
    try:
        stage = request.args.get("lifecycle_stage", "")
        keyword = request.args.get("keyword", "")
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))

        conn = get_db()

        where_clauses = []
        params_list = []

        if stage:
            where_clauses.append("lifecycle_stage = ?")
            params_list.append(stage)
        if keyword:
            where_clauses.append("(scenario LIKE ? OR extra_info LIKE ? OR content LIKE ?)")
            kw = f"%{keyword}%"
            params_list.extend([kw, kw, kw])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # 总数
        total = conn.execute(
            f"SELECT COUNT(*) as cnt FROM scripts WHERE {where_sql}",
            params_list
        ).fetchone()["cnt"]

        # 列表
        rows = conn.execute(
            f"SELECT id, lifecycle_stage, scenario, level, emotion, tone, extra_info, content, created_at FROM scripts WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params_list + [limit, offset]
        ).fetchall()

        items = []
        for row in rows:
            content = json.loads(row["content"]) if row["content"] else {}
            # 生成预览（前 50 字）
            full = f"{content.get('opening', '')}{content.get('core', '')}"
            preview = full[:50] + "..." if len(full) > 50 else full

            items.append({
                "id": row["id"],
                "lifecycle_stage": row["lifecycle_stage"],
                "scenario": row["scenario"],
                "level": row["level"],
                "emotion": row["emotion"],
                "tone": row["tone"],
                "preview": preview,
                "created_at": row["created_at"],
            })

        conn.close()
        return jsonify({"success": True, "total": total, "items": items})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/history/<int:script_id>", methods=["GET"])
def get_history_detail(script_id):
    try:
        conn = get_db()
        row = conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        conn.close()

        if not row:
            return jsonify({"success": False, "error": "记录不存在"}), 404

        content = json.loads(row["content"]) if row["content"] else {}
        predictions = json.loads(row["predictions"]) if row["predictions"] else []
        optimization = json.loads(row["optimization"]) if row["optimization"] else None

        return jsonify({
            "success": True,
            "id": row["id"],
            "lifecycle_stage": row["lifecycle_stage"],
            "scenario": row["scenario"],
            "level": row["level"],
            "emotion": row["emotion"],
            "tone": row["tone"],
            "extra_info": row["extra_info"],
            "script": content,
            "predictions": predictions,
            "optimization": optimization,
            "created_at": row["created_at"],
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/history/<int:script_id>", methods=["DELETE"])
def delete_history(script_id):
    try:
        conn = get_db()
        conn.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "已删除"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- 场景模板 ---

@app.route("/api/templates", methods=["GET"])
def get_templates():
    try:
        stage = request.args.get("lifecycle_stage", "")
        conn = get_db()
        if stage:
            rows = conn.execute(
                "SELECT * FROM templates WHERE lifecycle_stage = ? ORDER BY is_preset DESC, updated_at DESC",
                (stage,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM templates ORDER BY is_preset DESC, updated_at DESC"
            ).fetchall()
        conn.close()

        items = []
        for row in rows:
            items.append({
                "id": row["id"],
                "name": row["name"],
                "lifecycle_stage": row["lifecycle_stage"],
                "scenario": row["scenario"],
                "default_tone": row["default_tone"],
                "default_notes": row["default_notes"],
                "is_preset": bool(row["is_preset"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

        return jsonify({"success": True, "items": items})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/templates", methods=["POST"])
def create_template():
    try:
        params = request.get_json()
        required = ["name", "lifecycle_stage", "scenario"]
        for key in required:
            if not params.get(key):
                return jsonify({"success": False, "error": f"缺少必填参数：{key}"}), 400

        conn = get_db()
        cursor = conn.execute(
            """INSERT INTO templates (name, lifecycle_stage, scenario, default_tone, default_notes)
               VALUES (?, ?, ?, ?, ?)""",
            (
                params["name"],
                params["lifecycle_stage"],
                params["scenario"],
                params.get("default_tone", "正式严肃"),
                params.get("default_notes", ""),
            )
        )
        template_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({"success": True, "id": template_id, "message": "模板创建成功"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/templates/<int:template_id>", methods=["PUT"])
def update_template(template_id):
    try:
        params = request.get_json()
        conn = get_db()

        existing = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not existing:
            conn.close()
            return jsonify({"success": False, "error": "模板不存在"}), 404

        conn.execute(
            """UPDATE templates SET name=?, lifecycle_stage=?, scenario=?, default_tone=?, default_notes=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                params.get("name", existing["name"]),
                params.get("lifecycle_stage", existing["lifecycle_stage"]),
                params.get("scenario", existing["scenario"]),
                params.get("default_tone", existing["default_tone"]),
                params.get("default_notes", existing["default_notes"]),
                template_id,
            )
        )
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "模板更新成功"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/templates/<int:template_id>", methods=["DELETE"])
def delete_template(template_id):
    try:
        conn = get_db()
        existing = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not existing:
            conn.close()
            return jsonify({"success": False, "error": "模板不存在"}), 404
        if existing["is_preset"]:
            conn.close()
            return jsonify({"success": False, "error": "预置模板不可删除"}), 403

        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "模板已删除"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    insert_preset_templates()

    print("=" * 40)
    print("  ConflictCompass 服务已启动")
    print("  本机访问: http://127.0.0.1:5000")
    print("=" * 40)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
