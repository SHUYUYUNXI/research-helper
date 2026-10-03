# 研究与任务完成

## 产品口碑
先用 Exa 定位官方资料，再按用户关心的群体搜索 Twitter/Reddit 或小红书/B站。可用 `reachkit research "产品名 评价" --platforms exa,reddit,xiaohongshu --limit 5 --format md -o sources.md`。继续读取有实质内容的结果，区分官方说明、亲身使用和转述，最后回答用户问题并附来源。

## 技术选型
`reachkit research "技术关键词" --platforms github,bilibili,exa`；中文实践补掘金/CSDN/博客园文章。比较用途、更新情况、代码和限制，必要时用 gh code search、Issue/Actions 获取证据。维护旧集成的变更可能比星数更有帮助。

## 中文热点选题
读取百度热搜、少数派/开源中国、阮一峰周刊的列表，从相关条目继续读取正文，然后形成选题或对比。保留榜单时间与文章时间；不要把“热搜条目”当作已经核实的新闻事实。

## 招聘研究
按 career.md 准备真实已登录会话，搜索岗位并取 JD，再比较技能要求、地点和薪资。默认不向招聘方打招呼或投递。

## 来源归档
collect/research 会保留失败项和后端 attempts。Markdown/JSON 保留来源与获取时间，方便后续写作、对比和引用。结果只有摘要时，明确其信息粒度并继续读取关键原文。
