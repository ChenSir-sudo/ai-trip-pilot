"""pytest 配置：把仓库根目录放进 sys.path。

存在的唯一原因：本项目的包带 `src.` 前缀（见 docs/architecture.md §11 的目录结构），
而 pytest 默认只把测试文件所在目录加入 sys.path。根目录有这个文件之后，
测试里可以直接 `from src.graph... import`，不需要先把项目安装成包。

不做的事：不做任何 fixture 或全局设置——本步的测试全部零依赖，
    一旦在这里放共享 fixture，测试就开始依赖隐藏的上下文。
"""
