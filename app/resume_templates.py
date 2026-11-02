"""Job-family template catalogue.

Each entry pairs a visual system with the writing guidance of one job family,
so choosing a template also tells the user what that role's resume should carry.
Styles change presentation, never invent user facts.
"""

from typing import Literal

TemplateId = Literal[
    "classic",
    "technical",
    "backend",
    "algorithm",
    "modern",
    "product_mgr",
    "designer",
    "marketing",
    "sales",
    "finance",
    "hr",
    "teacher",
    "graduate",
    "medical",
    "legal",
    "engineer",
    "public_sector",
    "executive",
    "bilingual",
    "transition",
]

# Job-family order drives the catalogue navigation and the editor grouping.
TEMPLATE_TRACKS = (
    dict(id="tech", title="技术研发", note="后端 · 前端 · 算法 · 数据"),
    dict(id="product", title="产品与项目", note="产品 · 项目 · 解决方案"),
    dict(id="design", title="设计与创意", note="视觉 · 交互 · 内容创作"),
    dict(id="growth", title="市场与销售", note="市场 · 运营 · 销售 · 商务"),
    dict(id="finance", title="金融与财务", note="财务 · 审计 · 金融分析"),
    dict(id="hr", title="人力与行政", note="HR · 招聘 · 行政"),
    dict(id="education", title="教育与科研", note="教师 · 教研 · 应届校招"),
    dict(id="medical", title="医疗与健康", note="临床 · 护理 · 医技"),
    dict(id="legal", title="法律与合规", note="法务 · 合规 · 风控"),
    dict(id="engineering", title="工程与制造", note="结构 · 机械 · 电气 · 生产"),
    dict(id="public", title="公共事业", note="公务员 · 事业单位 · 国企"),
    dict(id="lead", title="管理与外企", note="总监 · 负责人 · 双语材料"),
    dict(id="switch", title="转行与跨领域", note="能力迁移 · 职业转换"),
)
TRACK_TITLES = {track["id"]: track["title"] for track in TEMPLATE_TRACKS}

SECTION_TITLES = {
    "summary": "个人总结",
    "experiences": "工作经历",
    "projects": "项目经历",
    "education": "教育经历",
    "skills": "技能特长",
    "certificates": "证书资质",
    "languages": "语言能力",
}

# Section headings a template may rename to match its job family.
SECTION_LABEL_OVERRIDES = {
    "medical": {"experiences": "临床经历", "projects": "质量改进与项目"},
    "teacher": {"experiences": "教学经历", "projects": "教研与课程"},
    "legal": {"experiences": "执业经历", "projects": "代表项目与案例"},
    "finance": {"certificates": "资质与证书"},
    "engineering": {"experiences": "项目与工作经历"},
    "graduate": {"experiences": "实习经历", "projects": "校园项目"},
}


def _guide(order, emphasis, tips, avoid):
    return dict(order=order, emphasis=emphasis, tips=tips, avoid=avoid)


_STANDARD_ORDER = [
    "summary",
    "experiences",
    "projects",
    "education",
    "skills",
    "certificates",
    "languages",
]

TEMPLATE_CATALOG = (
    dict(
        id="technical",
        title="技术项目",
        note="前端 · 全栈 · 工程化",
        category="tech",
        sample="fullstack",
        description="深色技术身份区与编号章节，项目居中展示，适合强调技术栈与交付细节。",
        benefit="技术身份区 / 编号章节",
        guide=_guide(
            _STANDARD_ORDER,
            "让面试官在 15 秒内看到技术栈、系统规模和你的角色。",
            [
                "每条经历写清「什么系统 + 你的动作 + 一个可验证的指标」。",
                "技术栈只列真正用过的，按熟练度排序，不堆名词。",
                "项目段落写清架构约束（流量、并发、数据量），比形容词有说服力。",
            ],
            "不要写「精通」却没有对应项目；不要把团队成果全写成个人成果。",
        ),
    ),
    dict(
        id="backend",
        title="后端服务",
        note="后端 · 服务端 · 架构",
        category="tech",
        sample="backend",
        description="深靛蓝单栏结构，章节带细线标记，强调稳定性、性能与链路治理。",
        benefit="稳定性叙事 / 链路视角",
        guide=_guide(
            _STANDARD_ORDER,
            "后端简历的核心是稳定性与性能，用故障率、延迟和成本说话。",
            [
                "优先写 QPS、P95 延迟、可用性、资损率这类可核对的数字。",
                "架构改造要写清改造前后的对比，而不是只写「重构了系统」。",
                "把监控、告警、预案这类治理工作单独成句，体现责任边界。",
            ],
            "避免只罗列框架名；避免把「参与」写成「主导」。",
        ),
    ),
    dict(
        id="algorithm",
        title="算法数据",
        note="算法 · 数据科学 · 机器学习",
        category="tech",
        sample="algorithm",
        description="靛紫色调配等宽标签，模型与实验信息分区呈现，突出指标与链路。",
        benefit="模型指标 / 实验闭环",
        guide=_guide(
            _STANDARD_ORDER,
            "算法岗看的是「指标提升多少」和「链路你负责哪一段」。",
            [
                "每段经历写清模型位置（召回 / 粗排 / 精排）与数据集规模。",
                "指标要写基线、提升幅度和统计口径，例如 CTR +6.2%。",
                "把离线评估、A/B 实验、上线监控写成闭环，体现工程落地能力。",
            ],
            "不要只写论文或课程项目；不要把离线指标当作线上收益。",
        ),
    ),
    dict(
        id="modern",
        title="简约现代",
        note="产品 · 设计 · 内容",
        category="product",
        sample="product",
        description="侧栏身份区与宽松留白，阅读节奏轻，适合产品与创意类岗位。",
        benefit="身份侧栏 / 轻盈留白",
        guide=_guide(
            _STANDARD_ORDER,
            "产品岗要证明你定义过什么，以及定义之后发生了什么变化。",
            [
                "用「问题—方案—结果」三段式写项目，结果必须可量化。",
                "写清协作范围（设计、研发、运营各几人），体现推动力。",
                "技能区分「方法」与「工具」，方法比工具更保值。",
            ],
            "避免把需求列表当成果；避免只写功能上线而不写使用情况。",
        ),
    ),
    dict(
        id="product_mgr",
        title="产品经理",
        note="B 端 · C 端 · 增长产品",
        category="product",
        sample="product",
        description="双色标题带与成果行，模块边界清晰，适合展示多段产品线与数据结果。",
        benefit="成果前置 / 模块清晰",
        guide=_guide(
            _STANDARD_ORDER,
            "先给结论再给过程：一句话说清你负责的产品服务多少人、带来什么变化。",
            [
                "个人总结控制在 3 行内，写行业、年限、最擅长的一类问题。",
                "每段经历至少一个业务指标（转化、留存、效率、成本）。",
                "把「需求评审、灰度、复盘」这类方法写进项目，体现完整闭环。",
            ],
            "不要用「负责跟进」这类无信息量的动词开头。",
        ),
    ),
    dict(
        id="designer",
        title="设计作品集",
        note="视觉 · 品牌 · UI/UX",
        category="design",
        sample="design",
        description="大字号标题与作品链接前置，留白充足，方便招聘方直接跳到作品。",
        benefit="作品优先 / 大字号",
        guide=_guide(
            _STANDARD_ORDER,
            "设计简历本身就是一个作品，排版克制比装饰更重要。",
            [
                "在个人信息里放作品集链接，并在项目里给出可访问地址。",
                "每个项目写清你的角色、设计目标与上线后的业务结果。",
                "列出工具与设计方法（规范、组件、可用性测试），而不只是软件名。",
            ],
            "不要用花哨字体和过多颜色；不要把团队作品署名为个人。",
        ),
    ),
    dict(
        id="marketing",
        title="增长运营",
        note="市场 · 运营 · 内容 · 增长",
        category="growth",
        sample="marketing",
        description="暖橙强调色与指标条，活动与数据并列，适合运营与市场岗位。",
        benefit="指标条 / 活动叙事",
        guide=_guide(
            _STANDARD_ORDER,
            "运营简历的说服力来自「花了多少钱、带来多少结果」。",
            [
                "每段经历写清预算规模、覆盖人群和最终转化。",
                "活动类项目用「目标—策略—执行—复盘」四步写，避免流水账。",
                "把数据能力写具体：SQL、漏斗、留存、A/B 实验各做到什么程度。",
            ],
            "不要只写「负责公众号运营」而不写增长结果。",
        ),
    ),
    dict(
        id="sales",
        title="销售业绩",
        note="大客户 · 渠道 · 商务拓展",
        category="growth",
        sample="sales",
        description="酒红强调色与业绩标签，客户与金额信息前置，适合销售与 BD。",
        benefit="业绩前置 / 客户视角",
        guide=_guide(
            _STANDARD_ORDER,
            "销售简历第一屏必须出现数字：签约额、完成率、客户数。",
            [
                "用「目标 / 实际 / 完成率」三件套写业绩，连续多年更佳。",
                "写清客户类型与决策链（行业、规模、采购角色）。",
                "渠道与生态类成果单独成段，体现可复制性。",
            ],
            "不要只写「负责区域销售」；不要把团队业绩算作个人业绩。",
        ),
    ),
    dict(
        id="classic",
        title="经典商务",
        note="通用 · 商务 · 行政 · 社招",
        category="growth",
        sample="product",
        description="单栏标准阅读顺序，稳重克制，适合大多数社招与商务岗位。",
        benefit="稳重单栏 / 清晰层级",
        guide=_guide(
            _STANDARD_ORDER,
            "通用型简历的目标是「不扣分」：结构清楚、时间连续、信息完整。",
            [
                "时间线必须连续，空档期用一句话说明（进修、家庭、求职）。",
                "每段经历 2–4 条要点，第一条写职责范围，其余写结果。",
                "联系方式保持可拨打、可送达，邮箱避免使用非正式昵称。",
            ],
            "不要为了凑页数加无关经历；不要使用超过两种字体。",
        ),
    ),
    dict(
        id="finance",
        title="财务审计",
        note="财务 · 审计 · 税务 · 金融分析",
        category="finance",
        sample="finance",
        description="墨蓝配金的严谨版式，资质与技能分区，适合财务、审计与金融岗。",
        benefit="严谨版式 / 资质前置",
        guide=_guide(
            [
                "summary",
                "experiences",
                "certificates",
                "skills",
                "projects",
                "education",
                "languages",
            ],
            "财务岗先看资质与合规经验，再看你经手的规模。",
            [
                "写清金额量级与业务范围（收入规模、科目、事业部数量）。",
                "证书按含金量排序，在考的注明已通过科目。",
                "内控、审计、税务合规类经验单独成条，体现风险意识。",
            ],
            "不要夸大证书状态；不要写与财务无关的兼职经历占篇幅。",
        ),
    ),
    dict(
        id="hr",
        title="人力行政",
        note="HRBP · 招聘 · 行政 · 培训",
        category="hr",
        sample="hr",
        description="暖棕圆角与柔和分区，亲和但不松散，适合人力与行政岗位。",
        benefit="柔和分区 / 组织视角",
        guide=_guide(
            _STANDARD_ORDER,
            "人力简历要体现你支持的组织规模，以及你改变了哪些人效指标。",
            [
                "写清支持团队人数、岗位类型与招聘交付量。",
                "绩效、盘点、员工关系类项目写清方法与落地范围。",
                "用留存率、到岗周期、满意度等指标证明结果。",
            ],
            "不要在简历里披露前雇主的具体薪酬与员工隐私信息。",
        ),
    ),
    dict(
        id="teacher",
        title="教师教研",
        note="中小学 · 高校 · 教研 · 培训",
        category="education",
        sample="teacher",
        description="青绿章节标签与课程信息区，教学、教研、育人三条线清楚分开。",
        benefit="教学三线 / 课程信息",
        guide=_guide(
            [
                "summary",
                "experiences",
                "education",
                "certificates",
                "skills",
                "projects",
                "languages",
            ],
            "教师简历看三件事：教得怎么样、教研做了什么、带班情况如何。",
            [
                "写清学段、学科、班级数与周课时，让工作量可感知。",
                "教学成果用分数、排名、获奖和公开课级别说明。",
                "教师资格证、普通话等级放在显眼位置。",
            ],
            "不要只写「热爱教育」；不要列出与学生隐私相关的具体信息。",
        ),
    ),
    dict(
        id="graduate",
        title="校园起点",
        note="应届 · 实习 · 校园项目",
        category="education",
        sample="campus",
        description="紧凑身份带与清晰的教育、实习、项目段落，适合没有全职经验的应届生。",
        benefit="信息带 / 明确章节",
        guide=_guide(
            [
                "summary",
                "education",
                "experiences",
                "projects",
                "skills",
                "certificates",
                "languages",
            ],
            "应届简历用「教育 + 实习 + 项目」三块证明你能上手做事。",
            [
                "教育经历写 GPA、排名、核心课程，只要对岗位有帮助。",
                "实习写清你独立完成的部分，而不是公司简介。",
                "课程项目要有产出（报告、模型、作品链接），不要只写题目。",
            ],
            "不要编造实习；不要用「熟悉 Office」占满技能栏。",
        ),
    ),
    dict(
        id="medical",
        title="临床护理",
        note="临床 · 护理 · 医技 · 药师",
        category="medical",
        sample="medical",
        description="洁净青蓝与资质前置结构，操作技能与执业证书分区，符合医疗行业习惯。",
        benefit="资质前置 / 操作清单",
        guide=_guide(
            [
                "summary",
                "certificates",
                "experiences",
                "education",
                "skills",
                "projects",
                "languages",
            ],
            "医疗岗先看执业资质与科室年限，再看具体操作能力。",
            [
                "把执业证、专科培训证、职称放在第一屏，写清取得时间。",
                "写清科室、床位/患者规模与独立完成的操作用例。",
                "质量改进与带教经历单独成条，体现专业影响力。",
            ],
            "不要披露患者身份信息；不要写未取得的资质。",
        ),
    ),
    dict(
        id="legal",
        title="法律合规",
        note="法务 · 律师 · 合规 · 风控",
        category="legal",
        sample="legal",
        description="墨黑衬线字体与细线分隔，正式克制，适合法律与合规岗位。",
        benefit="正式衬线 / 案例导向",
        guide=_guide(
            [
                "summary",
                "experiences",
                "certificates",
                "projects",
                "skills",
                "education",
                "languages",
            ],
            "法律岗先看资质与执业年限，再看你处理过什么类型的案件或合同。",
            [
                "法律职业资格、执业证与专业方向写在前两行。",
                "案例只写可公开的信息：案由、争议金额区间、你的角色与结果。",
                "合同与合规体系类工作写清覆盖范围和落地效果。",
            ],
            "不要披露当事人信息；不要写尚未结案的案件结论。",
        ),
    ),
    dict(
        id="engineer",
        title="工程技术",
        note="结构 · 机械 · 电气 · 生产",
        category="engineering",
        sample="engineering",
        description="工业灰蓝与参数行布局，项目带规模参数，适合工程与制造岗位。",
        benefit="参数行 / 项目规模",
        guide=_guide(
            _STANDARD_ORDER,
            "工程简历的关键是项目规模、专业软件与规范熟悉度。",
            [
                "写清项目建筑面积、层数、设备参数或产线规模。",
                "列出真正熟练的专业软件（YJK、PKPM、Revit、SolidWorks 等）。",
                "注册资格与职称放在显眼位置，注明是否在考。",
            ],
            "不要写「熟悉规范」却不提具体规范名称与版本。",
        ),
    ),
    dict(
        id="public_sector",
        title="规范简洁",
        note="公务员 · 事业单位 · 国企",
        category="public",
        sample="public",
        description="规则的信息网格与紧凑段落，正式规范；请以招聘方实际格式要求为准。",
        benefit="信息网格 / 正式排版",
        guide=_guide(
            [
                "summary",
                "education",
                "experiences",
                "skills",
                "certificates",
                "projects",
                "languages",
            ],
            "体制内材料重在规范、完整、时间连续，格式服从招考公告。",
            [
                "姓名、政治面貌、学历、专业按公告要求的字段顺序填写。",
                "工作经历写清单位、岗位、职责与年度考核结果。",
                "获奖与表彰按级别排列，写清颁发单位与年份。",
            ],
            "不要使用花哨排版；不要遗漏公告要求的必填项。",
        ),
    ),
    dict(
        id="executive",
        title="资深叙事",
        note="总监 · 负责人 · 资深专家",
        category="lead",
        sample="executive",
        description="醒目姓名与宽阔标题区，段落分组沉稳，突出经营结果与管理幅度。",
        benefit="宽幅标题 / 经营视角",
        guide=_guide(
            _STANDARD_ORDER,
            "高管简历只回答两个问题：你管多大盘子，你把结果做到了什么程度。",
            [
                "开篇写清管理幅度（团队人数、预算、业务规模）。",
                "每段经历给出 1–2 个经营级结果，例如营收、利润、人效。",
                "把组织建设与机制沉淀写出来，体现可复制性。",
            ],
            "不要堆砌日常事务；不要把公司整体成绩说成个人成绩。",
        ),
    ),
    dict(
        id="bilingual",
        title="中英标题",
        note="外企 · 双语材料 · 海外岗位",
        category="lead",
        sample="bilingual",
        description="中英双语章节标题，正文保留原文，不自动翻译或补写你的经历。",
        benefit="中英标题 / 原文保留",
        guide=_guide(
            _STANDARD_ORDER,
            "外企简历要双语可读：标题双语，正文写你真正能开口讲的内容。",
            [
                "职位名称用目标公司的通用英文表述，避免直译。",
                "章节标题保持双语一致，正文语言全篇统一。",
                "补充 LinkedIn 或作品链接，方便海外招聘方核实。",
            ],
            "不要让机器翻译正文；不要混用中英标点。",
        ),
    ),
    dict(
        id="transition",
        title="能力迁移",
        note="转行 · 跨领域 · 二次择业",
        category="switch",
        sample="transition",
        description="时间轴式章节与能力线索，方便对照旧经历与新岗位的共同点。",
        benefit="时间轴阅读 / 能力线索",
        guide=_guide(
            _STANDARD_ORDER,
            "转行简历的任务是翻译：把旧经历翻译成新岗位听得懂的语言。",
            [
                "个人总结直接说明转岗动机与已完成的准备（课程、项目、证书）。",
                "旧经历只保留可迁移的部分，弱化与新岗位无关的细节。",
                "用一个新领域的实战项目证明你不是从零开始。",
            ],
            "不要隐瞒转行事实；不要把旧岗位名称改成新岗位名称。",
        ),
    ),
)
# Layout skeletons. A template picks one skeleton plus options; the tpl-* skin
# layer only handles colour and type. This keeps layouts structurally different
# (two-column rails, timelines, banner headers, editorial numbering) instead of
# being re-coloured copies of the same single-column flow.
LAYOUT_LINEAR = "linear"
LAYOUT_SPLIT = "split"
LAYOUT_TIMELINE = "timeline"
LAYOUT_BANNER = "banner"
LAYOUT_EDITORIAL = "editorial"

# Rail sections live in the sidebar column of split layouts; everything else
# (summary, experiences, projects, education, custom) stays in the main column.
RAIL_SECTIONS = ("skills", "certificates", "languages")

LAYOUT_PLAN = {
    # linear: classic reading flow, ruled head.
    "classic": dict(layout=LAYOUT_LINEAR, options=dict(head="ruled")),
    "finance": dict(layout=LAYOUT_LINEAR, options=dict(head="centered")),
    "legal": dict(layout=LAYOUT_LINEAR, options=dict(head="plain")),
    "public_sector": dict(layout=LAYOUT_LINEAR, options=dict(head="grid")),
    "bilingual": dict(layout=LAYOUT_LINEAR, options=dict(head="plain")),
    # split: identity/skills rail + main column; side and tone vary.
    "modern": dict(
        layout=LAYOUT_SPLIT, options=dict(side="left", rail="soft", skills="list")
    ),
    "technical": dict(
        layout=LAYOUT_SPLIT, options=dict(side="right", rail="solid", skills="pills")
    ),
    "backend": dict(layout=LAYOUT_SPLIT, options=dict(side="left", rail="solid", skills="list")),
    "algorithm": dict(layout=LAYOUT_SPLIT, options=dict(side="right", rail="tint", skills="dots")),
    "sales": dict(layout=LAYOUT_SPLIT, options=dict(side="left", rail="solid", skills="pills")),
    "hr": dict(layout=LAYOUT_SPLIT, options=dict(side="right", rail="tint", skills="list")),
    "medical": dict(layout=LAYOUT_SPLIT, options=dict(side="left", rail="tint", skills="list")),
    "engineer": dict(layout=LAYOUT_SPLIT, options=dict(side="left", rail="soft", skills="meter")),
    # timeline: dated spine down the body.
    "product_mgr": dict(layout=LAYOUT_TIMELINE, options=dict(head="left")),
    "teacher": dict(layout=LAYOUT_TIMELINE, options=dict(head="centered")),
    "transition": dict(layout=LAYOUT_TIMELINE, options=dict(head="left")),
    # banner: full-width coloured header band, linear body below.
    "executive": dict(layout=LAYOUT_BANNER, options=dict(tone="solid")),
    "graduate": dict(layout=LAYOUT_BANNER, options=dict(tone="band")),
    # editorial: oversized name, lead paragraph, numbered chapters.
    "designer": dict(layout=LAYOUT_EDITORIAL, options=dict(numbered=True)),
    "marketing": dict(layout=LAYOUT_EDITORIAL, options=dict(numbered=True)),
}

TEMPLATE_IDS = tuple(item["id"] for item in TEMPLATE_CATALOG)
TEMPLATES_BY_ID = {item["id"]: item for item in TEMPLATE_CATALOG}

for _entry in TEMPLATE_CATALOG:
    _labels = {**SECTION_TITLES, **SECTION_LABEL_OVERRIDES.get(_entry["id"], {})}
    _entry["guide"]["order_titles"] = [_labels.get(key, key) for key in _entry["guide"]["order"]]
    _entry["labels"] = dict(SECTION_LABEL_OVERRIDES.get(_entry["id"], {}))
    _entry["layout"], _entry["options"] = LAYOUT_PLAN.get(
        _entry["id"], {"layout": LAYOUT_LINEAR, "options": {}}
    )["layout"], LAYOUT_PLAN.get(_entry["id"], {"layout": LAYOUT_LINEAR, "options": {}})["options"]


def template_entry(template_id: str):
    return TEMPLATES_BY_ID.get(template_id)


def template_visual(template_id: str) -> dict:
    """Serialize what the browser needs to draw a template."""
    entry = TEMPLATES_BY_ID.get(template_id) or TEMPLATES_BY_ID["classic"]
    return {
        "id": entry["id"],
        "title": entry["title"],
        "category": entry["category"],
        "layout": entry["layout"],
        "options": entry["options"],
        "labels": SECTION_LABEL_OVERRIDES.get(entry["id"], {}),
    }


def layout_for(template_id: str) -> dict:
    """Return {layout, options} for a template, defaulting to the linear flow."""
    plan = LAYOUT_PLAN.get(template_id)
    return {"layout": plan["layout"], "options": plan["options"]} if plan else {
        "layout": LAYOUT_LINEAR,
        "options": {"head": "plain"},
    }


def templates_by_track():
    """Group the catalogue by job family, keeping the declared track order."""
    grouped = []
    for track in TEMPLATE_TRACKS:
        items = [item for item in TEMPLATE_CATALOG if item["category"] == track["id"]]
        if items:
            grouped.append({**track, "templates": items})
    return grouped
