"""V1 template catalogue; styles change presentation, never invent user facts."""

from typing import Literal

TemplateId = Literal[
    "classic",
    "technical",
    "modern",
    "executive",
    "graduate",
    "transition",
    "public_sector",
    "bilingual",
]
TEMPLATE_CATALOG = (
    dict(
        id="classic",
        title="经典商务",
        note="社招 · 商务 · 行政",
        description="单栏标准阅读顺序，适合完整展开工作经历。",
        benefit="稳重单栏 / 清晰层级",
    ),
    dict(
        id="technical",
        title="技术项目",
        note="研发 · 算法 · 数据",
        description="技术标题与项目层级更明确，保留全部真实内容。",
        benefit="技术字标 / 项目阅读",
    ),
    dict(
        id="modern",
        title="简约现代",
        note="产品 · 设计 · 内容",
        description="侧栏身份区与轻盈留白，让内容易于浏览。",
        benefit="身份侧栏 / 轻盈留白",
    ),
    dict(
        id="executive",
        title="资深叙事",
        note="资深社招 · 业务负责人",
        description="醒目姓名、宽阔标题区与分组段落，突出经历的连续性。",
        benefit="宽幅标题 / 沉稳叙事",
    ),
    dict(
        id="graduate",
        title="校园起点",
        note="应届 · 实习 · 校园项目",
        description="紧凑身份带与清晰的教育项目段落，方便呈现真实校园经历。",
        benefit="信息带 / 明确章节",
    ),
    dict(
        id="transition",
        title="能力迁移",
        note="转行 · 跨领域求职",
        description="时间与职责层级分开呈现，方便对照可迁移能力。",
        benefit="时间轴阅读 / 能力线索",
    ),
    dict(
        id="public_sector",
        title="规范简洁",
        note="国企 · 行政 · 正式申请",
        description="规则的联系信息网格和紧凑段落；请以招聘方实际格式要求为准。",
        benefit="信息网格 / 正式排版",
    ),
    dict(
        id="bilingual",
        title="中英标题",
        note="外企 · 双语材料",
        description="中英双语章节标题，不自动翻译或补写你的经历正文。",
        benefit="中英标题 / 原文保留",
    ),
)
TEMPLATE_IDS = tuple(item["id"] for item in TEMPLATE_CATALOG)
