#!/usr/bin/env python3
"""Seeds sample BUPT campus data for testing and development."""

import json
import os
from datetime import datetime, timedelta

SEED_DATA = [
    # === 教务通知 (Academic Notices) ===
    {
        "id": "acad_001",
        "title": "2024-2025学年第二学期选课通知",
        "content": "各位同学：2024-2025学年第二学期选课工作即将开始。选课时间为2025年1月6日至1月10日，请登录教务系统（jwxt.bupt.edu.cn）进行选课。选课分为三轮：第一轮为预选（1月6-7日），第二轮为正选（1月8-9日），第三轮为补退选（1月10日）。请注意：每学期选课学分上限为30学分，必修课已预置无需选择。如有选课问题请联系教务处（西土城路10号教1楼213室，电话：010-62282045）。",
        "category": "academic",
        "source_url": "https://jwc.bupt.edu.cn/notice/001",
        "published_at": "2025-01-02T09:00:00Z",
        "author": "教务处"
    },
    {
        "id": "acad_002",
        "title": "关于2024-2025学年第一学期期末考试安排的通知",
        "content": "期末考试时间为2025年1月13日至1月24日。考试地点请查看教务系统中的个人考试安排。请携带学生证和身份证参加考试。考试期间如有特殊情况需请假，请提前向学院教务办公室提交书面申请。违反考试纪律者将按照《北京邮电大学学生考试违纪处分办法》处理。补考安排将在下学期开学第一周公布。",
        "category": "academic",
        "source_url": "https://jwc.bupt.edu.cn/notice/002",
        "published_at": "2025-01-05T10:00:00Z",
        "author": "教务处"
    },
    {
        "id": "acad_003",
        "title": "转专业申请通知",
        "content": "根据《北京邮电大学本科生转专业管理办法》，符合条件的本科生可以申请转专业。申请时间：每年3月1日至3月15日。申请条件：1）在校学习满一学期；2）无不及格课程；3）无违纪处分。申请流程：登录教务系统提交申请→学院审核→接收学院面试→教务处公示。每个学院转入名额一般不超过该年级该专业人数的15%。详情请咨询教务处教学运行科。",
        "category": "academic",
        "source_url": "https://jwc.bupt.edu.cn/notice/003",
        "published_at": "2025-02-20T08:00:00Z",
        "author": "教务处"
    },
    {
        "id": "acad_004",
        "title": "2025年研究生招生复试安排",
        "content": "2025年硕士研究生招生复试将于3月下旬进行。复试包括专业课笔试、英语听力及口语测试、综合面试三部分。请考生关注研究生院网站获取具体复试时间和地点。复试需携带：准考证、身份证、学生证（应届生）、学历证书（往届生）、本科成绩单。",
        "category": "academic",
        "source_url": "https://grs.bupt.edu.cn/notice/001",
        "published_at": "2025-03-01T09:00:00Z",
        "author": "研究生院"
    },
    {
        "id": "acad_005",
        "title": "关于开展毕业设计（论文）中期检查的通知",
        "content": "各学院：请组织2025届本科毕业生进行毕业设计中期检查。检查时间为3月17日至3月28日。学生需提交中期报告，指导教师填写评语。中期检查不合格的学生需在一周内提交整改方案。毕业论文最终提交截止日期为5月15日。",
        "category": "academic",
        "source_url": "https://jwc.bupt.edu.cn/notice/005",
        "published_at": "2025-03-10T14:00:00Z",
        "author": "教务处"
    },
    # === 图书馆 (Library) ===
    {
        "id": "lib_001",
        "title": "北京邮电大学图书馆开放时间",
        "content": "图书馆开放时间：周一至周五 8:00-22:00，周六周日 9:00-21:00。自习室开放时间：7:00-22:30（含节假日）。各楼层功能：1层为总服务台和电子阅览室，2层为社科阅览室，3层为自然科学阅览室，4层为期刊阅览室和研讨室，5层为特藏室和学位论文阅览室。借阅规则：本科生可借10册，研究生可借15册，借期30天，可续借一次。",
        "category": "library",
        "source_url": "https://lib.bupt.edu.cn/info/001",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "图书馆"
    },
    {
        "id": "lib_002",
        "title": "图书馆研讨室预约说明",
        "content": "图书馆4层设有12间研讨室，可供3-8人小组学习使用。预约方式：登录图书馆网站（lib.bupt.edu.cn）→研讨室预约系统。每次预约时长2小时，每人每天最多预约1次。预约后需在15分钟内到达，否则自动取消。使用期间请保持安静，不得饮食。如需取消预约，请提前1小时操作。",
        "category": "library",
        "source_url": "https://lib.bupt.edu.cn/info/002",
        "published_at": "2025-01-15T10:00:00Z",
        "author": "图书馆"
    },
    # === 校园服务 (Campus Services) ===
    {
        "id": "svc_001",
        "title": "校园食堂信息",
        "content": "北邮共有3个食堂：第一食堂（学1楼旁）营业时间：早餐6:30-9:00，午餐11:00-13:00，晚餐17:00-19:00；第二食堂（学3楼旁）营业时间相同；教工食堂（行政楼1层）仅供教职工使用。第一食堂1层为大众餐厅，2层为特色窗口（麻辣烫、砂锅、铁板饭等），3层为清真餐厅。第二食堂1层为大众餐厅，2层设有小炒和西餐窗口。校园卡充值点位于各食堂入口处。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/canteen",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "后勤处"
    },
    {
        "id": "svc_002",
        "title": "校医院服务指南",
        "content": "校医院位于学校西门附近。门诊时间：周一至周五 8:00-11:30, 13:30-17:00。周六上午 8:00-11:30（仅内科）。急诊24小时开放。科室设置：内科、外科、口腔科、眼科、皮肤科、中医科。学生就诊需携带校园卡和医保卡。常规体检每年9月进行。心理咨询中心位于校医院2楼，预约电话：010-62281001。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/hospital",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "校医院"
    },
    {
        "id": "svc_003",
        "title": "物业报修流程",
        "content": "宿舍报修流程：1）登录「北邮e修」微信小程序；2）选择报修类型（水电、家具、门窗、网络等）；3）填写宿舍楼栋和房间号；4）描述故障情况并上传照片；5）提交后会生成报修单号。维修人员会在24小时内响应，48小时内完成维修。如遇紧急情况（如漏水、断电），请直接拨打24小时应急电话：010-62282222。报修进度可在小程序中实时查看。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/repair",
        "published_at": "2025-01-10T09:00:00Z",
        "author": "后勤处"
    },
    {
        "id": "svc_004",
        "title": "校车班次时刻表",
        "content": "北邮校车连接西土城路校区和沙河校区。发车时间：西土城→沙河：7:00, 8:00, 12:00, 13:00, 17:30；沙河→西土城：7:30, 12:30, 13:30, 17:00, 21:00。行程约45分钟。乘车地点：西土城校区北门、沙河校区南门。凭校园卡免费乘坐。周末和节假日班次减半，具体以校园通知为准。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/bus",
        "published_at": "2025-02-01T08:00:00Z",
        "author": "后勤处"
    },
    {
        "id": "svc_005",
        "title": "校园网使用指南",
        "content": "北邮校园网覆盖全校区域。连接方式：1）有线网络：宿舍网口直连，使用学号和密码登录；2）无线网络：SSID为BUPT-portal，打开浏览器输入认证页面登录。每月免费流量20GB，超出部分0.5元/GB。网速限制：上行10Mbps，下行50Mbps。VPN服务：校外访问校内资源请使用 vpn.bupt.edu.cn。网络故障报修电话：010-62283333。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/network",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "信息化处"
    },
    # === 学生活动 (Student Activities) ===
    {
        "id": "act_001",
        "title": "北邮第二十届科技文化节开幕",
        "content": "一年一度的北邮科技文化节将于2025年4月12日拉开帷幕！本届主题为「智联未来」。活动包括：人工智能创新大赛、网络安全攻防赛（CTF）、机器人展示、开源项目路演、技术讲座系列、创业项目展。报名时间：3月20日至4月5日。报名方式：关注「北邮学生会」公众号，点击菜单栏「科文节报名」。各项赛事均设有丰厚奖品。",
        "category": "activity",
        "source_url": "https://youth.bupt.edu.cn/act/001",
        "published_at": "2025-03-15T10:00:00Z",
        "author": "校团委"
    },
    {
        "id": "act_002",
        "title": "名师讲坛：5G与未来通信技术",
        "content": "讲座主题：5G-Advanced与6G愿景。主讲人：张平教授（北邮信息与通信工程学院院长、IEEE Fellow）。时间：2025年3月25日（周二）14:00-16:00。地点：教3楼报告厅。面向全校师生开放，无需报名。张平教授将分享5G商用进展、6G关键技术方向及北邮在通信领域的最新研究成果。",
        "category": "activity",
        "source_url": "https://youth.bupt.edu.cn/act/002",
        "published_at": "2025-03-18T08:00:00Z",
        "author": "信息与通信工程学院"
    },
    {
        "id": "act_003",
        "title": "春季运动会报名通知",
        "content": "2025年北邮春季田径运动会将于4月26-27日在沙河校区田径场举行。比赛项目：100米、200米、400米、800米、1500米、5000米、4×100米接力、跳高、跳远、铅球、标枪。报名时间：3月25日至4月10日，请各学院体育委员汇总名单提交至体育部。每人最多报3个单项和1个接力。",
        "category": "activity",
        "source_url": "https://youth.bupt.edu.cn/act/003",
        "published_at": "2025-03-20T09:00:00Z",
        "author": "体育部"
    },
    {
        "id": "act_004",
        "title": "社团招新：北邮开源社",
        "content": "北邮开源社（BUPT OSS Club）招新啦！我们是北邮最活跃的技术社团之一，致力于推广开源文化和技术交流。活动内容：每周技术分享、开源项目协作、黑客马拉松、技术博客撰写。欢迎所有对编程和开源感兴趣的同学加入！报名方式：扫描海报二维码或搜索QQ群：123456789。",
        "category": "activity",
        "source_url": "https://youth.bupt.edu.cn/act/004",
        "published_at": "2025-03-01T15:00:00Z",
        "author": "北邮开源社"
    },
    # === 行政服务 FAQ ===
    {
        "id": "faq_001",
        "title": "学生证补办流程",
        "content": "学生证遗失后补办流程：1）在校园网登录学工系统提交挂失申请；2）3个工作日后携带身份证到学生事务中心（学活1层）领取新学生证；3）火车票优惠资质需重新办理，携带新学生证到教务处盖章。补办费用：10元/次。临时学生证明可在自助打印机上打印，有效期7天。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/faq/001",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "学生事务中心"
    },
    {
        "id": "faq_002",
        "title": "奖学金评定办法",
        "content": "北京邮电大学奖学金分为：1）国家奖学金（8000元/年，成绩排名前5%）；2）校级一等奖学金（3000元/年，前10%）；3）校级二等奖学金（2000元/年，前25%）；4）校级三等奖学金（1000元/年，前40%）。评定时间：每年10月。评定依据：学业成绩（70%）+ 综合表现（30%）。申请流程：个人申请→班级评议→学院审核→学校公示。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/faq/002",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "学生事务中心"
    },
    {
        "id": "faq_003",
        "title": "宿舍管理规定",
        "content": "北邮学生宿舍管理规定：1）门禁时间：23:00-6:00；2）禁止使用大功率电器（超过800W），包括电吹风（宿舍楼公共区域可使用）、电热毯、电火锅等；3）不得留宿外来人员；4）保持宿舍卫生，每月检查一次；5）网络使用遵守国家法律法规。违规行为将按照《学生手册》处理。紧急情况联系宿管：各楼值班室。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/faq/003",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "学生公寓管理中心"
    },
    {
        "id": "faq_004",
        "title": "出国交流项目介绍",
        "content": "北邮现有出国交流项目：1）学期交换（与英国伦敦玛丽女王大学、美国纽约州立大学等合作）；2）暑期学校（剑桥、牛津、MIT等）；3）联合培养双学位项目。申请条件：GPA≥3.0，英语成绩达标（雅思6.5或托福85以上）。申请时间：春季项目10月申请，秋季项目3月申请。详情请咨询国际交流与合作处（行政楼4层）。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/faq/004",
        "published_at": "2025-02-01T00:00:00Z",
        "author": "国际交流与合作处"
    },
    {
        "id": "faq_005",
        "title": "校园卡使用说明",
        "content": "校园卡功能：食堂消费、图书借阅、门禁通行、校车乘坐、打印复印。充值方式：1）食堂充值机（现金/银行卡）；2）微信关注「北邮校园卡」小程序在线充值；3）支付宝生活号充值。挂失方式：微信小程序挂失或到卡务中心（学活1层）办理。补卡费用：20元。每日消费限额：200元。",
        "category": "service",
        "source_url": "https://service.bupt.edu.cn/faq/005",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "信息化处"
    },
    # === 校园地图与建筑 ===
    {
        "id": "map_001",
        "title": "北邮西土城路校区建筑指南",
        "content": "主要建筑位置：教学楼：教1楼（主楼东侧）、教2楼（图书馆北侧）、教3楼（校区东北角）、教4楼（新建，校区西北侧）。行政楼位于校区中心。图书馆位于校区中部。学生宿舍区位于校区南部（学1-学13楼）。食堂位于宿舍区旁。实验楼群位于校区北部。体育馆位于校区西侧。校医院位于西门附近。",
        "category": "campus",
        "source_url": "https://www.bupt.edu.cn/map",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "校办"
    },
    {
        "id": "map_002",
        "title": "教务处及各行政办公室位置",
        "content": "教务处位于教1楼2层（213室），工作时间：周一至周五 8:30-11:30, 14:00-17:00。学生事务中心位于学生活动中心1层。研究生院位于行政楼3层。财务处位于行政楼1层。国际交流与合作处位于行政楼4层。就业指导中心位于学生活动中心2层。心理咨询中心位于校医院2层。",
        "category": "campus",
        "source_url": "https://www.bupt.edu.cn/offices",
        "published_at": "2025-01-01T00:00:00Z",
        "author": "校办"
    },
    # === 招生信息 ===
    {
        "id": "adm_001",
        "title": "2025年本科招生简章",
        "content": "北京邮电大学2025年计划招收本科生3600人。优势专业：通信工程、计算机科学与技术、信息安全、人工智能、数据科学与大数据技术、电子商务。录取原则：按照高考成绩从高到低录取，专业志愿间无级差。咨询电话：010-62282045。开放日：6月中旬。详细招生计划请关注北邮招生网：zsb.bupt.edu.cn。",
        "category": "admission",
        "source_url": "https://zsb.bupt.edu.cn/notice/001",
        "published_at": "2025-03-01T00:00:00Z",
        "author": "招生办"
    },
    # === 科研信息 ===
    {
        "id": "res_001",
        "title": "国家自然科学基金项目申报通知",
        "content": "2025年度国家自然科学基金项目申报工作已启动。请有意申报的教师于3月10日前将申请书电子版提交至科研处邮箱。本年度重点支持方向：6G通信、人工智能安全、量子信息、空天地一体化网络。青年基金申请人年龄要求：男性35周岁以下，女性38周岁以下。",
        "category": "research",
        "source_url": "https://keyan.bupt.edu.cn/notice/001",
        "published_at": "2025-02-15T09:00:00Z",
        "author": "科研处"
    },
    # === 就业信息 ===
    {
        "id": "job_001",
        "title": "2025春季校园招聘会",
        "content": "2025年春季大型校园招聘会将于3月22日（周六）9:00-16:00在体育馆举行。参会企业超过200家，涵盖通信、互联网、金融科技、人工智能等领域。知名企业包括：华为、中兴、腾讯、阿里巴巴、字节跳动、中国移动等。请同学们提前准备简历，着正装参加。详细企业名录请关注就业指导中心公众号。",
        "category": "employment",
        "source_url": "https://job.bupt.edu.cn/notice/001",
        "published_at": "2025-03-10T10:00:00Z",
        "author": "就业指导中心"
    },
    {
        "id": "job_002",
        "title": "实习信息：华为2025暑期实习招聘",
        "content": "华为2025暑期实习生招聘面向全校开放。岗位方向：软件开发、算法研究、网络工程、产品经理、测试工程、AI研究。实习时间：2025年7-9月，每月实习补贴5000-8000元。申请方式：登录华为招聘官网投递简历，北邮专场面试将于4月中旬进行。",
        "category": "employment",
        "source_url": "https://job.bupt.edu.cn/notice/002",
        "published_at": "2025-03-12T14:00:00Z",
        "author": "就业指导中心"
    },
]


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "seed_data.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(SEED_DATA, f, ensure_ascii=False, indent=2)

    print(f"Seeded {len(SEED_DATA)} documents to {output_path}")

    # Print summary by category
    from collections import Counter
    categories = Counter(doc["category"] for doc in SEED_DATA)
    print("\nDocuments by category:")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
