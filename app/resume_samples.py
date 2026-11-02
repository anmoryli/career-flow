"""Sample resumes per job family.

Every template shows a sample that matches the job it targets, so the preview
teaches the expected shape of that role instead of showing one generic person.
All facts here are fictional and never written into a user's resume.
"""

from types import MappingProxyType

_PHONE = "138 0000 0000"
_MAIL = "example@example.com"

SAMPLE_PROFILES = MappingProxyType(
    {
        "backend": {
            "name": "王砚",
            "role": "后端开发工程师",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "杭州",
            "github": "github.com/example-backend",
            "website": "",
            "linkedin": "",
            "summary": (
                "5 年服务端研发经验，负责交易与订单链路的设计与治理。"
                "习惯用可观测数据定位问题，关注接口稳定性与成本。"
            ),
            "experiences": [
                {
                    "company": "云启科技",
                    "role": "后端开发工程师",
                    "period": "2021.03 — 至今",
                    "location": "杭州",
                    "bullets": [
                        "主导订单服务从单体拆分为 4 个微服务，接口 P95 由 820ms 降至 190ms。",
                        "设计分布式锁与幂等方案，重复下单率从 0.7% 降到 0.02%。",
                        "搭建监控告警与链路追踪，故障平均定位时间由 40 分钟缩短到 8 分钟。",
                    ],
                },
                {
                    "company": "承知网络",
                    "role": "后端开发工程师",
                    "period": "2019.07 — 2021.02",
                    "location": "上海",
                    "bullets": [
                        "负责会员与支付模块，支撑日均 30 万笔订单，全年可用性 99.97%。",
                        "引入消息队列削峰，大促峰值写入能力提升至原来的 3 倍。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "订单中台重构",
                    "role": "核心开发",
                    "period": "2023.04 — 2023.11",
                    "tech": "Go · MySQL · Redis · Kafka",
                    "description": "拆分下单、履约、结算三条链路，"
                    "补齐幂等与对账能力；上线后资损工单下降 76%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例理工大学",
                    "degree": "软件工程 · 本科",
                    "period": "2015 — 2019",
                    "detail": "主修数据结构、操作系统与数据库系统；毕业设计为分布式任务调度平台。",
                }
            ],
            "skills": [
                {"label": "语言", "items": ["Go", "Java", "Python"]},
                {"label": "存储", "items": ["MySQL", "Redis", "Elasticsearch"]},
                {"label": "架构", "items": ["微服务", "消息队列", "领域建模"]},
                {"label": "工程", "items": ["Docker", "Kubernetes", "CI/CD"]},
            ],
            "certificates": ["软件设计师（中级）", "AWS 解决方案架构师（助理级）"],
            "languages": ["中文（母语）", "英语（技术文档阅读）"],
        },
        "algorithm": {
            "name": "周懿",
            "role": "算法工程师 · 推荐方向",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "北京",
            "github": "github.com/example-algo",
            "website": "",
            "linkedin": "",
            "summary": (
                "4 年推荐与排序算法经验，负责召回、粗排到重排的完整链路。"
                "重视离线指标与线上实验的闭环，习惯把结论写成可复用的评估报告。"
            ),
            "experiences": [
                {
                    "company": "示例内容平台",
                    "role": "算法工程师",
                    "period": "2022.04 — 至今",
                    "location": "北京",
                    "bullets": [
                        "负责首页召回与排序，人均停留时长提升 12.4%，次日留存提升 1.9 个百分点。",
                        "上线双塔召回模型，千万级候选集单次检索耗时下降 45%。",
                        "搭建离线评估与 A/B 实验流程，单次实验周期由 2 周缩短到 3 天。",
                    ],
                },
                {
                    "company": "示例智能科技",
                    "role": "算法工程师",
                    "period": "2020.06 — 2022.03",
                    "location": "北京",
                    "bullets": [
                        "完成文本分类与实体抽取模型，F1 从 0.81 提升到 0.89。",
                        "整理标注规范与质检流程，标注返工率下降 30%。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "多路召回融合",
                    "role": "负责人",
                    "period": "2023.02 — 2023.08",
                    "tech": "PyTorch · Faiss · Spark",
                    "description": "将协同过滤、向量召回与热度召回加权融合，线上 CTR 提升 6.2%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例大学",
                    "degree": "计算机科学与技术 · 硕士",
                    "period": "2017 — 2020",
                    "detail": "研究方向为信息检索；参与实验室与企业的联合推荐项目。",
                }
            ],
            "skills": [
                {"label": "模型", "items": ["推荐系统", "CTR 预估", "向量召回"]},
                {"label": "框架", "items": ["PyTorch", "TensorFlow", "Spark"]},
                {"label": "工程", "items": ["Python", "Faiss", "特征工程"]},
                {"label": "评估", "items": ["A/B 实验", "离线指标", "误差分析"]},
            ],
            "certificates": ["全国大学生数学建模竞赛 省级一等奖"],
            "languages": ["中文（母语）", "英语（论文阅读与写作）"],
        },
        "fullstack": {
            "name": "李澈",
            "role": "全栈工程师",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "深圳",
            "github": "github.com/example-fullstack",
            "website": "example.dev",
            "linkedin": "",
            "summary": (
                "6 年 B 端产品研发经验，能独立完成从需求拆解、前端交互到服务端接口的交付。"
                "关注工程效率与可维护性，长期维护团队共用的组件库。"
            ),
            "experiences": [
                {
                    "company": "示例 SaaS 公司",
                    "role": "全栈工程师",
                    "period": "2020.09 — 至今",
                    "location": "深圳",
                    "bullets": [
                        "负责客户管理模块的前后端实现，服务 1.2 万家企业账号。",
                        "沉淀 38 个业务组件，新页面平均开发时间从 5 天缩短到 2 天。",
                        "推动接口契约与自动化测试落地，线上回归缺陷下降 42%。",
                    ],
                },
                {
                    "company": "示例软件工作室",
                    "role": "前端工程师",
                    "period": "2018.07 — 2020.08",
                    "location": "广州",
                    "bullets": [
                        "完成 6 个企业官网与后台系统交付，均按期上线。",
                        "把重复的表格与表单逻辑抽成模板，项目启动成本降低约一半。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "可视化配置平台",
                    "role": "技术负责人",
                    "period": "2022.05 — 2022.12",
                    "tech": "React · TypeScript · Node.js",
                    "description": "用拖拽方式配置审批表单，业务方自助完成 70% 的表单调整需求。",
                    "link": "example.dev/form-builder",
                },
                {
                    "name": "业务组件库",
                    "role": "维护者",
                    "period": "2021.03 — 至今",
                    "tech": "Vite · Storybook · Vitest",
                    "description": "提供统一的表格、筛选与图表组件，被 5 条产品线复用。",
                    "link": "example.dev/ui",
                },
            ],
            "education": [
                {
                    "school": "示例工业大学",
                    "degree": "计算机科学与技术 · 本科",
                    "period": "2014 — 2018",
                    "detail": "主修 Web 开发与数据库；担任校技术社团负责人。",
                }
            ],
            "skills": [
                {"label": "前端", "items": ["React", "TypeScript", "CSS 架构"]},
                {"label": "后端", "items": ["Node.js", "Python", "REST API"]},
                {"label": "数据", "items": ["PostgreSQL", "Redis"]},
                {"label": "工程", "items": ["自动化测试", "CI/CD", "性能优化"]},
            ],
            "certificates": ["软件设计师（中级）"],
            "languages": ["中文（母语）", "英语（工作沟通）"],
        },
        "product": {
            "name": "林澄",
            "role": "高级产品经理",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "杭州",
            "website": "example.com/product",
            "github": "",
            "linkedin": "",
            "summary": (
                "6 年企业服务与数据产品经验，负责从需求洞察、方案设计到上线验证的完整链路。"
                "擅长把复杂业务流程整理为可衡量的产品方案。"
            ),
            "experiences": [
                {
                    "company": "示例科技",
                    "role": "高级产品经理",
                    "period": "2021.06 — 至今",
                    "location": "杭州",
                    "bullets": [
                        "负责企业协作产品的需求规划与迭代，服务 2.3 万家企业客户。",
                        "主导权限与审批模块重构，核心流程完成时长下降 28%。",
                        "建立用户访谈与迭代复盘机制，协同设计、研发与客户成功团队交付产品。",
                    ],
                },
                {
                    "company": "示范网络",
                    "role": "产品经理",
                    "period": "2018.07 — 2021.05",
                    "location": "上海",
                    "bullets": [
                        "从 0 到 1 搭建数据分析看板，覆盖 12 个业务团队。",
                        "梳理指标口径与埋点方案，完成需求评审、验收与上线培训。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "企业数据看板",
                    "role": "产品负责人",
                    "period": "2023",
                    "tech": "SQL · Tableau · Figma",
                    "description": "整合多源业务数据，提供自助分析能力；"
                    "上线后周活跃使用率提升 41%。",
                    "link": "example.com/dashboard",
                },
                {
                    "name": "审批流程配置平台",
                    "role": "产品负责人",
                    "period": "2022.03 — 2022.12",
                    "tech": "流程建模 · 权限设计 · 用户研究",
                    "description": "梳理跨部门审批场景，设计角色权限与可配置流程，"
                    "通过灰度验证持续迭代。",
                    "link": "",
                },
            ],
            "education": [
                {
                    "school": "示例大学",
                    "degree": "信息管理 · 本科",
                    "period": "2014 — 2018",
                    "detail": "主修数据库、统计分析与管理信息系统；获校级优秀毕业生。",
                }
            ],
            "skills": [
                {"label": "产品能力", "items": ["需求分析", "产品规划", "用户研究"]},
                {"label": "设计协作", "items": ["Figma", "流程建模", "跨团队沟通"]},
                {"label": "数据分析", "items": ["SQL", "Tableau", "指标体系"]},
                {"label": "交付方法", "items": ["敏捷迭代", "需求评审", "可用性测试"]},
            ],
            "certificates": ["PMP 项目管理专业人士", "数据分析专项课程结业"],
            "languages": ["中文（母语）", "英语（工作沟通）"],
        },
        "design": {
            "name": "苏白",
            "role": "品牌视觉设计师",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "上海",
            "website": "example.design",
            "github": "",
            "linkedin": "",
            "summary": (
                "6 年品牌与视觉设计经验，覆盖品牌识别、包装与线上线下物料。"
                "习惯先建立视觉规则，再让规则在多个渠道里稳定复用。"
            ),
            "experiences": [
                {
                    "company": "示例品牌设计事务所",
                    "role": "资深视觉设计师",
                    "period": "2020.05 — 至今",
                    "location": "上海",
                    "bullets": [
                        "主导 12 个品牌视觉升级项目，其中 3 个获行业设计奖项。",
                        "建立品牌视觉规范与素材库，跨渠道物料产出效率提升 40%。",
                        "与市场、电商团队协作完成 4 次大促主视觉，最高单场曝光 2600 万。",
                    ],
                },
                {
                    "company": "示例文创公司",
                    "role": "视觉设计师",
                    "period": "2018.07 — 2020.04",
                    "location": "杭州",
                    "bullets": [
                        "完成 30+ 款包装设计，2 款成为年度畅销单品。",
                        "负责社交媒体视觉模板，日常内容制作时间缩短一半。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "咖啡品牌视觉重塑",
                    "role": "主设计师",
                    "period": "2023.03 — 2023.09",
                    "tech": "Figma · Illustrator · 摄影指导",
                    "description": "重构标志、字体与包装体系；上线后门店客单价提升 9%，"
                    "社媒自然讨论量增长 2 倍。",
                    "link": "example.design/coffee",
                },
                {
                    "name": "设计规范手册",
                    "role": "编写者",
                    "period": "2022.01 — 2022.06",
                    "tech": "品牌识别 · 版式 · 色彩系统",
                    "description": "把标志用法、色彩与版式规则整理为 48 页手册，"
                    "供内外部供应商统一执行。",
                    "link": "example.design/guide",
                },
            ],
            "education": [
                {
                    "school": "示例美术学院",
                    "degree": "视觉传达设计 · 本科",
                    "period": "2014 — 2018",
                    "detail": "主修字体设计、品牌形象与版式设计；毕业作品留校展出。",
                }
            ],
            "skills": [
                {"label": "设计", "items": ["品牌识别", "字体排印", "版式设计"]},
                {"label": "工具", "items": ["Figma", "Illustrator", "Photoshop"]},
                {"label": "动效", "items": ["After Effects", "Lottie"]},
                {"label": "协作", "items": ["设计规范", "供应商管理", "评审主持"]},
            ],
            "certificates": ["Adobe 认证视觉设计专家"],
            "languages": ["中文（母语）", "英语（设计资料阅读）"],
        },
        "marketing": {
            "name": "陈默",
            "role": "用户增长运营",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "深圳",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "5 年电商与内容平台增长经验，负责拉新、留存与活动运营。"
                "习惯用分层和数据说话，把每一次投放与活动都做成可复盘的实验。"
            ),
            "experiences": [
                {
                    "company": "示例电商平台",
                    "role": "用户增长运营",
                    "period": "2021.08 — 至今",
                    "location": "深圳",
                    "bullets": [
                        "负责拉新与留存活动，年度新增用户 48 万，获客成本下降 23%。",
                        "搭建用户分层与触达策略，次月留存提升 6.8 个百分点。",
                        "主导 6 场大促活动，单场 GMV 峰值 1200 万元。",
                    ],
                },
                {
                    "company": "示例内容社区",
                    "role": "运营专员",
                    "period": "2019.07 — 2021.07",
                    "location": "广州",
                    "bullets": [
                        "负责社群从 0 到 1 运营，6 个月沉淀 3.2 万活跃用户。",
                        "设计内容激励规则，日均投稿量提升 2.4 倍。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "新客首单转化实验",
                    "role": "项目负责人",
                    "period": "2023.05 — 2023.08",
                    "tech": "SQL · 神策 · A/B 测试",
                    "description": "用 4 组券策略做并行实验，"
                    "确定最优组合后首单转化率提升 18%，券成本下降 11%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例财经大学",
                    "degree": "市场营销 · 本科",
                    "period": "2015 — 2019",
                    "detail": "主修消费者行为、市场调研与统计学；校级营销策划大赛二等奖。",
                }
            ],
            "skills": [
                {"label": "增长", "items": ["用户分层", "活动策划", "A/B 测试"]},
                {"label": "数据", "items": ["SQL", "漏斗分析", "留存分析"]},
                {"label": "内容", "items": ["短视频脚本", "社群运营"]},
                {"label": "投放", "items": ["巨量引擎", "信息流优化"]},
            ],
            "certificates": ["Google 数据分析证书"],
            "languages": ["中文（母语）", "英语（工作沟通）"],
        },
        "sales": {
            "name": "赵启",
            "role": "大客户销售经理",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "广州",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "7 年企业服务销售经验，负责制造业与零售行业大客户开发。"
                "擅长从业务痛点切入做方案销售，连续三年超额完成业绩目标。"
            ),
            "experiences": [
                {
                    "company": "示例云服务公司",
                    "role": "大客户销售经理",
                    "period": "2020.03 — 至今",
                    "location": "广州",
                    "bullets": [
                        "连续 3 年完成率超过 120%，2023 年个人签约额 860 万元。",
                        "开拓制造业客户 26 家，其中 5 家签订年度框架协议。",
                        "搭建区域渠道伙伴体系，渠道贡献占区域营收 35%。",
                    ],
                },
                {
                    "company": "示例软件公司",
                    "role": "销售代表",
                    "period": "2017.06 — 2020.02",
                    "location": "佛山",
                    "bullets": [
                        "负责 200+ 中小客户维护与续约，年度续约率 88%。",
                        "整理行业报价与方案模板，新人上手周期从 2 个月缩短到 3 周。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "制造业标杆客户攻坚",
                    "role": "销售负责人",
                    "period": "2022.09 — 2023.03",
                    "tech": "方案销售 · 招投标 · 商务谈判",
                    "description": "联合售前与交付团队完成 3 轮方案汇报，"
                    "签下年度 420 万元订单并复制到同园区 4 家企业。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例工商学院",
                    "degree": "工商管理 · 本科",
                    "period": "2013 — 2017",
                    "detail": "主修市场营销与商务谈判；担任校创业社团外联负责人。",
                }
            ],
            "skills": [
                {"label": "客户", "items": ["大客户开发", "方案销售", "商务谈判"]},
                {"label": "行业", "items": ["制造业", "企业服务", "招投标"]},
                {"label": "工具", "items": ["CRM", "销售漏斗管理"]},
                {"label": "语言", "items": ["粤语（流利）", "英语（商务沟通）"]},
            ],
            "certificates": ["销售管理专项培训结业"],
            "languages": ["中文（母语）", "英语（商务邮件）"],
        },
        "finance": {
            "name": "何宁",
            "role": "财务分析经理",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "上海",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "8 年制造业财务经验，负责预算、经营分析与成本改善。"
                "擅长把财务数据翻译成业务能理解的动作建议。"
            ),
            "experiences": [
                {
                    "company": "示例制造集团",
                    "role": "财务分析经理",
                    "period": "2020.04 — 至今",
                    "location": "上海",
                    "bullets": [
                        "负责年度预算编制与滚动预测，覆盖 5 个事业部、合计 12 亿元收入。",
                        "搭建产品毛利分析模型，识别 3 条低毛利产品线并推动调价，"
                        "毛利率提升 2.1 个百分点。",
                        "主导月度经营分析会材料，输出偏差原因与改善建议。",
                    ],
                },
                {
                    "company": "示例会计师事务所",
                    "role": "审计员",
                    "period": "2016.09 — 2020.03",
                    "location": "上海",
                    "bullets": [
                        "参与 15 家制造业企业年报审计，独立完成存货与成本循环测试。",
                        "梳理客户核算流程问题清单，2 家客户据此完成账务整改。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "标准成本体系建设",
                    "role": "项目负责人",
                    "period": "2022.03 — 2022.11",
                    "tech": "SAP · Excel 建模 · Power BI",
                    "description": "重新核定 6 条产线的工时与费率标准，"
                    "成本差异分析周期由 10 天缩短到 3 天。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例财经大学",
                    "degree": "会计学 · 本科",
                    "period": "2012 — 2016",
                    "detail": "主修财务会计、成本会计与审计学；连续三年获学业奖学金。",
                }
            ],
            "skills": [
                {"label": "核算", "items": ["合并报表", "成本核算", "税务申报"]},
                {"label": "分析", "items": ["预算编制", "滚动预测", "差异分析"]},
                {"label": "工具", "items": ["Excel 建模", "SAP", "Power BI"]},
                {"label": "合规", "items": ["企业会计准则", "内控流程"]},
            ],
            "certificates": ["中级会计职称", "CPA 专业阶段 4 科通过"],
            "languages": ["中文（母语）", "英语（财务报表阅读）"],
        },
        "hr": {
            "name": "吴恬",
            "role": "HRBP",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "北京",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "6 年互联网人力资源经验，支持研发与技术团队。"
                "在招聘交付、绩效校准与员工留存上都有完整落地经验。"
            ),
            "experiences": [
                {
                    "company": "示例互联网公司",
                    "role": "HRBP",
                    "period": "2020.06 — 至今",
                    "location": "北京",
                    "bullets": [
                        "支持 300 人研发团队，年度招聘交付 86 人，关键岗位到岗周期缩短 20%。",
                        "设计季度绩效校准流程，跨部门评分一致性明显提升。",
                        "组织年度员工调研，推动 3 项留存措施落地，主动离职率下降 4 个百分点。",
                    ],
                },
                {
                    "company": "示例科技公司",
                    "role": "招聘专员",
                    "period": "2018.07 — 2020.05",
                    "location": "北京",
                    "bullets": [
                        "负责技术岗位招聘，年面试 600+ 人次，offer 接受率 82%。",
                        "搭建候选人跟进表与面试官培训材料，面试反馈及时率提升到 95%。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "技术人才盘点",
                    "role": "项目负责人",
                    "period": "2023.02 — 2023.06",
                    "tech": "人才九宫格 · 述职评审 · 数据分析",
                    "description": "完成 120 人技术团队盘点，输出 18 人关键人才名单与接续计划。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例师范大学",
                    "degree": "人力资源管理 · 本科",
                    "period": "2014 — 2018",
                    "detail": "主修组织行为学、薪酬管理与劳动法；校级职业规划大赛一等奖。",
                }
            ],
            "skills": [
                {"label": "招聘", "items": ["需求分析", "面试评估", "雇主品牌"]},
                {"label": "组织", "items": ["绩效管理", "人才盘点", "员工关系"]},
                {"label": "数据", "items": ["人力数据分析", "编制测算"]},
                {"label": "工具", "items": ["北森", "飞书人事"]},
            ],
            "certificates": ["企业人力资源管理师（二级）"],
            "languages": ["中文（母语）", "英语（工作沟通）"],
        },
        "teacher": {
            "name": "沈清",
            "role": "高中语文教师",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "南京",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "7 年高中语文教学经验，带过两届毕业班。"
                "关注阅读与写作的贯通训练，长期参与校本课程建设与青年教师带教。"
            ),
            "experiences": [
                {
                    "company": "示例高级中学",
                    "role": "高中语文教师",
                    "period": "2019.08 — 至今",
                    "location": "南京",
                    "bullets": [
                        "承担 2 个班语文教学，所带班级高考平均分超省均 11 分。",
                        "主持校本课程《整本书阅读》，覆盖 6 个班级、约 300 名学生。",
                        "获市级优质课评比二等奖，指导学生获省级作文竞赛一等奖 3 人。",
                    ],
                },
                {
                    "company": "示例实验学校",
                    "role": "语文教师 / 班主任",
                    "period": "2017.08 — 2019.07",
                    "location": "苏州",
                    "bullets": [
                        "担任班主任，班级连续两学期获校级文明班级。",
                        "组织读书节与辩论社团，参与学生 200 余人次。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "议论文写作序列课程",
                    "role": "课程负责人",
                    "period": "2022.09 — 2023.06",
                    "tech": "课程设计 · 命题研究 · 学情分析",
                    "description": "把写作拆成 8 个训练单元，配套范例与评价量表；"
                    "年级作文均分提升 4.6 分。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例师范大学",
                    "degree": "汉语言文学（师范） · 本科",
                    "period": "2013 — 2017",
                    "detail": "主修中国古代文学、语文课程与教学论；教育实习获优秀实习生。",
                }
            ],
            "skills": [
                {"label": "教学", "items": ["课程设计", "课堂管理", "命题与评价"]},
                {"label": "教研", "items": ["集体备课", "课题研究", "公开课"]},
                {"label": "育人", "items": ["班级管理", "家校沟通", "心理疏导"]},
                {"label": "工具", "items": ["课件制作", "在线作业平台"]},
            ],
            "certificates": ["高级中学教师资格证（语文）", "普通话水平二级甲等"],
            "languages": ["中文（母语）", "英语（文献阅读）"],
        },
        "campus": {
            "name": "许知",
            "role": "应届毕业生 · 数据分析",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "武汉",
            "website": "",
            "github": "github.com/example-student",
            "linkedin": "",
            "summary": (
                "统计学专业应届生，做过两段数据分析实习。"
                "熟悉 SQL 与 Python 分析流程，能把一次分析从取数写到结论汇报。"
            ),
            "experiences": [
                {
                    "company": "示例互联网公司",
                    "role": "数据分析实习生",
                    "period": "2025.07 — 2025.10",
                    "location": "武汉",
                    "bullets": [
                        "负责活动效果分析，独立完成 12 份复盘报告，其中 3 条建议被采纳上线。",
                        "整理埋点口径文档，减少跨团队取数沟通成本。",
                    ],
                },
                {
                    "company": "示例咨询公司",
                    "role": "研究助理（实习）",
                    "period": "2025.01 — 2025.04",
                    "location": "武汉",
                    "bullets": [
                        "清洗并整理 8 万条问卷数据，输出行业分析图表 40 余张。",
                        "协助撰写调研报告 2 份，用于客户内部汇报。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "校园二手交易平台分析",
                    "role": "项目负责人",
                    "period": "2024.09 — 2025.01",
                    "tech": "Python · pandas · Tableau",
                    "description": "基于 1.2 万条交易记录分析供需结构，"
                    "提出 3 条运营建议，课程项目获评优秀。",
                    "link": "",
                },
                {
                    "name": "全国大学生统计建模大赛",
                    "role": "队长",
                    "period": "2024.05 — 2024.08",
                    "tech": "R · 回归建模 · 可视化",
                    "description": "完成城市消费活力评价模型，获省级二等奖。",
                    "link": "",
                },
            ],
            "education": [
                {
                    "school": "示例大学",
                    "degree": "统计学 · 本科",
                    "period": "2022 — 2026",
                    "detail": "主修概率论、回归分析与多元统计；GPA 3.7/4.0，专业前 10%。",
                }
            ],
            "skills": [
                {"label": "分析", "items": ["SQL", "Python", "R"]},
                {"label": "可视化", "items": ["Tableau", "Excel"]},
                {"label": "统计", "items": ["回归分析", "假设检验", "抽样"]},
                {"label": "办公", "items": ["PPT 汇报", "文档撰写"]},
            ],
            "certificates": ["全国大学生统计建模大赛 省级二等奖", "CET-6"],
            "languages": ["中文（母语）", "英语（CET-6，可阅读文献）"],
        },
        "medical": {
            "name": "顾宁",
            "role": "护师 · 重症监护",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "南京",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "7 年三甲医院重症护理经验，独立承担呼吸机、CRRT 等重症护理操作。"
                "参与科室护理质量改进与临床带教，注重操作规范与记录完整。"
            ),
            "experiences": [
                {
                    "company": "示例市第一人民医院",
                    "role": "护师（ICU）",
                    "period": "2019.08 — 至今",
                    "location": "南京",
                    "bullets": [
                        "负责 8 张重症床位的责任制护理，独立完成呼吸机、CRRT 等操作。",
                        "参与护理质量改进项目，导尿管相关感染率下降 30%。",
                        "承担 12 名实习护士带教，完成出科考核与操作示范。",
                    ],
                },
                {
                    "company": "示例市中心医院",
                    "role": "护士（急诊）",
                    "period": "2017.07 — 2019.07",
                    "location": "南京",
                    "bullets": [
                        "负责急诊分诊与抢救配合，年参与抢救 200 余例。",
                        "维护急救车与药品清点流程，季度检查零缺陷。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "重症患者早期活动方案",
                    "role": "项目成员",
                    "period": "2022.03 — 2022.10",
                    "tech": "循证护理 · 评估量表 · 多学科协作",
                    "description": "制定分级活动流程并培训 20 名护士；"
                    "实施后患者机械通气时间平均缩短 1.8 天。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例医科大学",
                    "degree": "护理学 · 本科",
                    "period": "2013 — 2017",
                    "detail": "主修内科护理学、外科护理学与急危重症护理学；临床实习 10 个月。",
                }
            ],
            "skills": [
                {"label": "临床", "items": ["重症监护", "静脉治疗", "急救配合"]},
                {"label": "文书", "items": ["护理记录", "交接班", "评估量表"]},
                {"label": "沟通", "items": ["患者沟通", "家属沟通", "多学科协作"]},
                {"label": "教学", "items": ["临床带教", "操作示范"]},
            ],
            "certificates": ["护士执业资格证", "重症专科护士培训合格证", "BLS 基础生命支持"],
            "languages": ["中文（母语）", "英语（文献阅读）"],
        },
        "legal": {
            "name": "程砚",
            "role": "企业法务主管",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "北京",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "6 年企业法务经验，覆盖合同管理、争议解决与数据合规。"
                "做法务的习惯是先看业务目标，再判断风险边界。"
            ),
            "experiences": [
                {
                    "company": "示例科技公司",
                    "role": "法务主管",
                    "period": "2021.05 — 至今",
                    "location": "北京",
                    "bullets": [
                        "负责合同审核，年均 800+ 份，建立标准合同库使平均审核时长缩短 40%。",
                        "主导 3 起商事诉讼与仲裁，累计挽回损失 460 万元。",
                        "搭建数据合规制度，完成 2 项个人信息保护影响评估。",
                    ],
                },
                {
                    "company": "示例律师事务所",
                    "role": "律师助理",
                    "period": "2018.07 — 2021.04",
                    "location": "北京",
                    "bullets": [
                        "协助办理民商事案件 30 余件，独立完成证据整理与法律检索。",
                        "撰写法律意见书与合同审查意见 60 余份。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "标准合同库建设",
                    "role": "项目负责人",
                    "period": "2022.04 — 2022.12",
                    "tech": "合同模板 · 审批流程 · 风险条款库",
                    "description": "梳理 9 类高频合同，沉淀 26 份模板与 40 条风险提示；"
                    "业务自助起草比例提升到 65%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例政法大学",
                    "degree": "法学 · 本科",
                    "period": "2014 — 2018",
                    "detail": "主修合同法、公司法与民事诉讼法；模拟法庭校队成员。",
                }
            ],
            "skills": [
                {"label": "合同", "items": ["起草", "审核", "谈判"]},
                {"label": "争议", "items": ["诉讼", "仲裁", "证据管理"]},
                {"label": "合规", "items": ["数据合规", "劳动用工", "内控制度"]},
                {"label": "语言", "items": ["英文合同审阅"]},
            ],
            "certificates": ["法律职业资格证书（A 证）", "企业合规师（中级）"],
            "languages": ["中文（母语）", "英语（合同审阅）"],
        },
        "engineering": {
            "name": "马骁",
            "role": "结构工程师",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "成都",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "7 年设计院结构设计经验，完成住宅、公建与装配式项目。"
                "熟悉混凝土与钢结构计算，能与建筑、机电及施工现场配合落地。"
            ),
            "experiences": [
                {
                    "company": "示例建筑设计院",
                    "role": "结构工程师",
                    "period": "2019.07 — 至今",
                    "location": "成都",
                    "bullets": [
                        "负责 6 个住宅与公建项目结构设计，最高为 32 层剪力墙结构。",
                        "使用 YJK、PKPM 完成整体计算与施工图，一次审图通过率 90%。",
                        "参与装配式项目，预制率达到 40%，完成节点详图与吊装配合。",
                    ],
                },
                {
                    "company": "示例工程公司",
                    "role": "结构设计助理",
                    "period": "2017.07 — 2019.06",
                    "location": "重庆",
                    "bullets": [
                        "完成 4 个项目的梁板配筋与楼梯详图绘制。",
                        "配合现场处理 20 余项设计变更，均形成闭环记录。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "示例科创园 A 地块",
                    "role": "结构专业负责人",
                    "period": "2022.06 — 2023.10",
                    "tech": "YJK · Revit · 装配式",
                    "description": "建筑面积 8.6 万平方米，采用框架-剪力墙体系；"
                    "通过优化柱网节省混凝土用量约 6%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例交通大学",
                    "degree": "土木工程 · 本科",
                    "period": "2013 — 2017",
                    "detail": "主修结构力学、混凝土结构设计与钢结构设计；毕业设计为高层住宅结构。",
                }
            ],
            "skills": [
                {"label": "设计", "items": ["混凝土结构", "钢结构", "装配式"]},
                {"label": "软件", "items": ["YJK", "PKPM", "AutoCAD", "Revit"]},
                {"label": "规范", "items": ["抗震设计", "荷载规范", "施工图审查"]},
                {"label": "协作", "items": ["图纸会审", "现场配合", "专业协调"]},
            ],
            "certificates": ["一级注册结构工程师（基础考试通过）", "中级工程师职称"],
            "languages": ["中文（母语）", "英语（技术资料阅读）"],
        },
        "public": {
            "name": "郑肃",
            "role": "综合管理岗",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "合肥",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "5 年政务服务中心窗口与综合管理经验，熟悉事项受理、材料审核与公文办理。"
                "工作中注重流程规范与群众沟通，年度考核均为称职以上。"
            ),
            "experiences": [
                {
                    "company": "示例区政务服务中心",
                    "role": "综合窗口岗",
                    "period": "2021.03 — 至今",
                    "location": "合肥",
                    "bullets": [
                        "负责 12 类事项受理，年办件 6000 余件，全年零有效投诉。",
                        "参与“一网通办”流程梳理，申请材料平均精简 35%。",
                        "承担窗口新人培训，编写 8 份业务操作指引。",
                    ],
                },
                {
                    "company": "示例街道办事处",
                    "role": "综合办公室工作人员",
                    "period": "2019.08 — 2021.02",
                    "location": "合肥",
                    "bullets": [
                        "负责公文收发与档案整理，年度归档 1200 余件。",
                        "参与文明创建活动组织，累计开展活动 20 余场。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "政务服务事项标准化梳理",
                    "role": "主要参与人",
                    "period": "2022.05 — 2023.01",
                    "tech": "流程梳理 · 材料清单 · 标准文本",
                    "description": "完成 46 项事项的受理标准与材料清单编写，"
                    "窗口一次性告知准确率提升到 98%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例大学",
                    "degree": "行政管理 · 本科",
                    "period": "2015 — 2019",
                    "detail": "主修公共政策、行政法与公文写作；在校期间任学生会办公室干事。",
                }
            ],
            "skills": [
                {"label": "公文", "items": ["通知", "总结", "报告"]},
                {"label": "业务", "items": ["事项受理", "政策解读", "档案管理"]},
                {"label": "办公", "items": ["Word", "Excel", "政务系统"]},
                {"label": "沟通", "items": ["群众接待", "部门协调"]},
            ],
            "certificates": ["普通话水平二级甲等", "计算机二级"],
            "languages": ["中文（母语）", "英语（基础阅读）"],
        },
        "executive": {
            "name": "方岭",
            "role": "运营总监",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "上海",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "15 年互联网运营与经营管理经验，带过 80 人跨职能团队。"
                "负责过从 3 亿到 8 亿的营收增长，擅长把战略拆解成可执行的季度动作。"
            ),
            "experiences": [
                {
                    "company": "示例生活服务集团",
                    "role": "运营总监",
                    "period": "2019.04 — 至今",
                    "location": "上海",
                    "bullets": [
                        "统管用户运营、商家运营与客服团队共 80 人，"
                        "年度营收从 3.2 亿增长到 8.1 亿。",
                        "重建经营分析例会机制，季度目标达成率由 76% 提升到 94%。",
                        "推动组织从职能制转为业务线制，关键岗位人效提升 28%。",
                    ],
                },
                {
                    "company": "示例电商公司",
                    "role": "运营高级经理",
                    "period": "2013.06 — 2019.03",
                    "location": "杭州",
                    "bullets": [
                        "负责品类运营，年 GMV 从 8000 万增长到 4.5 亿。",
                        "搭建商家分层与激励体系，头部商家续约率提升到 91%。",
                        "主导大促作战室机制，连续 6 次大促超额完成目标。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "经营分析体系搭建",
                    "role": "项目负责人",
                    "period": "2021.02 — 2021.10",
                    "tech": "指标体系 · 数据看板 · 经营例会",
                    "description": "统一 5 条业务线的核心指标口径，"
                    "建立周度看板与月度复盘，决策响应周期缩短一半。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例大学",
                    "degree": "工商管理 · 硕士",
                    "period": "2010 — 2013",
                    "detail": "研究方向为组织与战略管理；在校期间参与两家企业的管理咨询项目。",
                }
            ],
            "skills": [
                {"label": "经营", "items": ["战略拆解", "预算管理", "经营分析"]},
                {"label": "业务", "items": ["用户运营", "商家运营", "增长策略"]},
                {"label": "组织", "items": ["团队搭建", "绩效设计", "组织变革"]},
                {"label": "协作", "items": ["跨部门推动", "高层汇报"]},
            ],
            "certificates": ["高级管理人员工商管理研修班结业"],
            "languages": ["中文（母语）", "英语（商务沟通）"],
        },
        "bilingual": {
            "name": "李佳 / Grace Li",
            "role": "市场经理 / Marketing Manager",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "上海",
            "website": "",
            "github": "",
            "linkedin": "linkedin.com/in/example-grace",
            "summary": (
                "7 年外资消费品市场经验，负责品牌传播与新品上市。"
                "与亚太及全球团队协作完成 4 次跨国营销活动，熟悉双语工作环境。"
            ),
            "experiences": [
                {
                    "company": "示例消费品（中国）有限公司",
                    "role": "市场经理",
                    "period": "2020.07 — 至今",
                    "location": "上海",
                    "bullets": [
                        "负责品牌年度传播计划，管理 1200 万元预算，触达目标人群 1.8 亿人次。",
                        "主导 3 款新品上市，其中 1 款首年销售额进入品类前五。",
                        "与亚太团队共建内容素材库，区域物料本地化周期从 3 周缩短到 1 周。",
                    ],
                },
                {
                    "company": "示例日化公司",
                    "role": "品牌专员",
                    "period": "2017.08 — 2020.06",
                    "location": "上海",
                    "bullets": [
                        "负责社交媒体内容运营，账号粉丝从 3 万增长到 26 万。",
                        "支持 6 场线下快闪活动，单场平均到店 4000 人次。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "新品整合营销上市",
                    "role": "市场负责人",
                    "period": "2023.03 — 2023.09",
                    "tech": "整合营销 · 媒介投放 · KOL 合作",
                    "description": "联合电商与线下渠道做三波上市节奏，首月销量达成目标的 132%。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例外国语大学",
                    "degree": "英语（商务方向） · 本科",
                    "period": "2013 — 2017",
                    "detail": "主修商务英语、跨文化传播与市场营销；通过英语专业八级。",
                }
            ],
            "skills": [
                {"label": "品牌", "items": ["品牌传播", "新品上市", "内容策略"]},
                {"label": "渠道", "items": ["整合营销", "媒介投放", "KOL 合作"]},
                {"label": "语言", "items": ["英语（流利）", "中文（母语）"]},
                {"label": "工具", "items": ["Excel", "PowerPoint", "社媒分析"]},
            ],
            "certificates": ["英语专业八级（TEM-8）", "Google 数字营销证书"],
            "languages": ["中文（母语）", "英语（专业八级，工作语言）"],
        },
        "transition": {
            "name": "唐亦",
            "role": "用户运营（由教学转岗）",
            "phone": _PHONE,
            "email": _MAIL,
            "city": "成都",
            "website": "",
            "github": "",
            "linkedin": "",
            "summary": (
                "5 年中学教学经验，转岗用户运营。"
                "把课堂里的需求分析、内容设计效果评估，迁移到用户分层与社群运营场景。"
            ),
            "experiences": [
                {
                    "company": "示例在线教育公司",
                    "role": "用户运营（转岗）",
                    "period": "2024.03 — 至今",
                    "location": "成都",
                    "bullets": [
                        "负责 3 万学员社群的日常运营，月活跃率从 21% 提升到 34%。",
                        "设计分层触达策略，续费转化率提升 5.4 个百分点。",
                    ],
                },
                {
                    "company": "示例中学",
                    "role": "语文教师 / 班主任",
                    "period": "2019.08 — 2024.02",
                    "location": "成都",
                    "bullets": [
                        "带过 2 届毕业班，班级平均分连续两年高于年级均分。",
                        "独立设计 40 余节课件与练习，形成可复用的教学素材库。",
                        "通过家长沟通与学情反馈，班级满意度调查连续 4 学期超过 95%。",
                    ],
                },
            ],
            "projects": [
                {
                    "name": "自学转岗作品集",
                    "role": "个人项目",
                    "period": "2023.06 — 2024.01",
                    "tech": "SQL · Excel · 用户调研",
                    "description": "完成 3 份用户运营案例分析，"
                    "其中一份被面试方作为笔试题范例讨论。",
                    "link": "",
                }
            ],
            "education": [
                {
                    "school": "示例师范大学",
                    "degree": "汉语言文学（师范） · 本科",
                    "period": "2015 — 2019",
                    "detail": "主修课程与教学论、教育心理学；教育实习获优秀评价。",
                }
            ],
            "skills": [
                {"label": "可迁移", "items": ["需求分析", "内容设计", "效果评估"]},
                {"label": "运营", "items": ["社群运营", "用户分层", "活动策划"]},
                {"label": "数据", "items": ["SQL 基础", "Excel 分析"]},
                {"label": "沟通", "items": ["家长沟通", "跨部门协作"]},
            ],
            "certificates": ["高级中学教师资格证（语文）", "用户运营系统课程结业"],
            "languages": ["中文（母语）", "英语（基础阅读）"],
        },
    }
)


def sample_for(template_id: str) -> dict:
    """Return the sample document for a template, falling back to the product one."""
    from app.resume_templates import template_entry

    entry = template_entry(template_id)
    key = entry.get("sample", "product") if entry else "product"
    sample = _copy(SAMPLE_PROFILES.get(key, SAMPLE_PROFILES["product"]))
    if entry:
        sample["section_order"] = list(entry["guide"]["order"])
    sample.setdefault("hidden_sections", [])
    sample["size"] = "standard"
    sample["accent"] = "default"
    sample["photo_position"] = "center"
    return sample


def sample_map() -> dict:
    """Every template's sample, keyed by template id, for the editor preview."""
    from app.resume_templates import TEMPLATE_IDS

    return {template_id: sample_for(template_id) for template_id in TEMPLATE_IDS}


def _copy(value):
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value
