import os
import sys

project = 'SSD I/O 学习记录'
copyright = '2026, lin-wind'
author = 'lin-wind'

pygments_style = "one-dark"     # 处理代码块的颜色
master_doc = 'index'

html_theme = 'sphinx_clarity_theme'

html_static_path = ['_static']
html_css_files = ['custom.css']

extensions = [
    'myst_parser',              # 解析 Markdown (.md)
    'sphinxcontrib.mermaid',    # 渲染 Mermaid 流程图
]

# 支持的文件后缀
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}

# 开启 Markdown 扩展 
myst_enable_extensions = [
    "dollarmath",
    "amsmath",
    "colon_fence",
    "deflist",
]




