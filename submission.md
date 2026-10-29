# 队伍49751：GitHub仓库准备

- 赛道：RTL；私有仓库名：`49751_rtlagent`；默认分支：`main`。
- 当前智能体：`2026.10.29-v11.1-qwen-only`，待固定千问实测。
- 主模型：`Qwen3-14B-Q4_K_M`，固定配置见`manifest.json`及`model/MODEL.md`。
- 方案包直接放在仓库根目录，官方基线原文件保留。源码、技能、测试和说明随仓库保存。
- Git不包含模型权重、真实令牌、API密钥、许可证、EDA运行目录和原始运行日志。
- 官方规则核对：2026-10-29远端master仍为`fc8e26a5828b7222e9db439cee29128bcf4f8865`。

官方要求在2026-10-31 10:00（北京时间）前完成私有仓库上传、邀请GitHub账号`vickyiii`，
并启动投题服务。赛事方拉取默认分支的提交作为封存版本。
2026-11-04 18:00前还须向比赛系统提交报告、视频和同一仓库链接。
本文记录要求，不表示仓库邀请、云端运行或比赛系统提交已完成。

部署顺序：按`model/MODEL.md`准备固定权重与官方镜像依赖，按`serve/README.md`配置
同一Qwen服务和本地权重路径；运行`bash serve/start.sh`，再运行
`bash serve/run_api.sh start`。真实投题令牌通过实例环境变量配置，不能写进本仓库。
本轮只准备仓库，不以历史实测代替当前版本部署验收。

历史报告有指向开发工作区的原始证据链接；原始日志和EDA产物不随Git上传。
V11.1的本地315项回归及归档重放范围见`docs/v11p1_regression_fix_20261029.md`。

官方依据：
[提交说明](https://gitee.com/Vickyiii/rtlagent2026/blob/fc8e26a5828b7222e9db439cee29128bcf4f8865/docs/SUBMISSION.md)，
[方案包结构](https://gitee.com/Vickyiii/rtlagent2026/blob/fc8e26a5828b7222e9db439cee29128bcf4f8865/README.md)。
