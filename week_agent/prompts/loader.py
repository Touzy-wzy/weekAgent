"""提示词模板加载器"""

import os
from pathlib import Path


def load_prompt_template(template_name: str, prompts_dir: str = "week_agent/prompts") -> str:
    """Load prompt template from markdown file.
    
    Args:
        template_name: 模板名称（不含 .md 后缀），如 "flowus"、"weekly_report"、"log_monitor"
        prompts_dir: 提示词文件目录路径，默认为 "week_agent/prompts"
    
    Returns:
        模板内容字符串
    
    Raises:
        FileNotFoundError: 模板文件不存在时抛出
        ValueError: 模板名称为空时抛出
    
    Examples:
        >>> flowus_prompt = load_prompt_template("flowus")
        >>> weekly_prompt = load_prompt_template("weekly_report")
        >>> log_prompt = load_prompt_template("log_monitor")
    """
    if not template_name:
        raise ValueError("模板名称不能为空")
    
    # 构建文件路径
    file_path = os.path.join(prompts_dir, f"{template_name}.md")
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"提示词模板文件不存在: {file_path}")
    
    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def get_available_templates(prompts_dir: str = "week_agent/prompts") -> list:
    """获取可用的模板列表。
    
    Args:
        prompts_dir: 提示词文件目录路径
    
    Returns:
        模板名称列表（不含 .md 后缀）
    """
    templates = []
    if os.path.exists(prompts_dir):
        for file in os.listdir(prompts_dir):
            if file.endswith('.md'):
                templates.append(file[:-3])  # 去掉 .md 后缀
    return sorted(templates)


# 便捷函数：直接获取常用模板
def get_flowus_prompt(prompts_dir: str = "week_agent/prompts") -> str:
    """获取 FlowUs 系统提示词模板"""
    return load_prompt_template("flowus", prompts_dir)


def get_weekly_report_prompt(prompts_dir: str = "week_agent/prompts") -> str:
    """获取周报生成提示词模板"""
    return load_prompt_template("weekly_report", prompts_dir)


def get_log_monitor_prompt(prompts_dir: str = "week_agent/prompts") -> str:
    """获取日志监控系统提示词模板"""
    return load_prompt_template("log_monitor", prompts_dir)


if __name__ == "__main__":
    # 测试加载器
    print("可用模板:", get_available_templates())
    print()
    
    try:
        flowus = get_flowus_prompt()
        print("FlowUs 模板长度:", len(flowus))
        
        weekly = get_weekly_report_prompt()
        print("周报模板长度:", len(weekly))
        
        log = get_log_monitor_prompt()
        print("日志监控模板长度:", len(log))
        
    except FileNotFoundError as e:
        print(f"错误: {e}")
    except Exception as e:
        print(f"其他错误: {e}")