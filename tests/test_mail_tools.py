"""邮件工具的集成测试"""

import json
from hello_agents.tools.response import ToolStatus
from week_agent.agent.tools import AgentlyComposeMailTool, AgentlySendMailTool


def test_compose_mail():
    """测试邮件编写工具"""
    print("\n=== 测试邮件编写工具 ===\n")

    tool = AgentlyComposeMailTool()

    # 测试有效参数
    response = tool.run({
        "to": "test@example.com",
        "subject": "测试邮件",
        "body": "这是一封测试邮件内容"
    })

    print(f"状态: {response.status}")
    print(f"文本: {response.text}")
    if response.data:
        print(f"数据: {json.dumps(response.data, indent=2, ensure_ascii=False)}")

    if response.status == ToolStatus.SUCCESS:
        print("\n[OK] 邮件编写工具测试通过")
        return response.data.get("confirmation_token")
    else:
        print(f"\n[FAIL] 邮件编写工具测试失败: {response.error_info}")
        return None


def test_send_mail(confirmation_token: str):
    """测试邮件发送工具"""
    print("\n=== 测试邮件发送工具 ===\n")

    tool = AgentlySendMailTool()

    response = tool.run({
        "to": "test@example.com",
        "subject": "测试邮件",
        "body": "这是一封测试邮件内容",
        "confirmation_token": confirmation_token
    })

    print(f"状态: {response.status}")
    print(f"文本: {response.text}")
    if response.data:
        print(f"数据: {json.dumps(response.data, indent=2, ensure_ascii=False)}")

    if response.status == ToolStatus.SUCCESS:
        print("\n[OK] 邮件发送工具测试通过")
        return True
    else:
        print(f"\n[FAIL] 邮件发送工具测试失败: {response.error_info}")
        return False


def test_invalid_params():
    """测试无效参数"""
    print("\n=== 测试无效参数处理 ===\n")

    tool = AgentlyComposeMailTool()

    # 测试空参数
    test_cases = [
        ({"to": "", "subject": "主题", "body": "内容"}, "收件人为空"),
        ({"to": "user@example.com", "subject": "", "body": "内容"}, "主题为空"),
        ({"to": "user@example.com", "subject": "主题", "body": ""}, "内容为空"),
    ]

    for params, description in test_cases:
        response = tool.run(params)
        if response.status == ToolStatus.ERROR:
            print(f"[OK] {description}: {response.error_info['message']}")
        else:
            print(f"[FAIL] {description}: 应该失败但成功了")


if __name__ == "__main__":
    print("邮件工具集成测试开始...\n")

    # 测试无效参数
    test_invalid_params()

    # 测试邮件编写
    token = test_compose_mail()

    if token:
        # 测试邮件发送
        test_send_mail(token)

    print("\n测试完成！")
