<p align="center"><img src="docs/logo.svg" width="880" alt="Cloud9 OmniRoute"></p>

# Cloud9-OmniRoute

**官方 [OmniRoute](https://github.com/cheaper-inference/OmniRoute) 最新稳定版，附带通用兼容性增强，由 GitHub 构建 GHCR 镜像。**

[English](README.md) · [Français](README.fr.md) · 简体中文

![架构图](docs/architecture.svg)

不复制官方应用的完整源码，每次都以最新官方稳定发布为基础。增强功能包括：修复 Cleanroom/ChatGPT Web 的 CSP 浏览器桥接；提供 1 到 4 张内嵌 Gemini JPEG/PNG/WebP 参考图，不抓取远程 URL；仅对 OMNIROUTE_STRICT_TOOL_RESPONSE_PROVIDERS 配置的严格 OpenAI 兼容供应商修改工具回复的 name 字段；保留 OAuth 与配额条件的 Codex 图像支持；Cloud9 Engine 与 Speaches 品牌图标。

GitHub Actions 检查补丁、功能及正式构建，发布不可变候选镜像。未经模型、OAuth、图片、Cleanroom、数据及回滚测试，不自动发布 latest 或部署生产环境。

仓库与镜像无个人信息、API 密钥、Cookie、私有域名或用户数据。特定配置保存在私有环境中。MIT 许可证。
