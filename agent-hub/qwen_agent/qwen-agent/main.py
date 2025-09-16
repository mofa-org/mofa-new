from mofa.agent_build.base.base_agent import MofaAgent, run_agent
import os
from dotenv import load_dotenv
from dashscope import Generation
import logging

# --------------------------
# 日志配置（显示调试信息，便于定位问题）
# --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@run_agent
def run(agent: MofaAgent):
    try:
        # --------------------------
        # 1. 加载环境变量与输入校验
        # --------------------------
        # 加载 .env.secret 中的配置（API 密钥、模型名等）
        load_dotenv('.env.secret')
        
        # 接收用户输入（从 terminal-input 传递的 'query' 参数）
        user_input = agent.receive_parameter('query')
        logger.info(f"Received user input: {user_input}")
        
        # 校验用户输入是否为空
        if not user_input or user_input.strip() == "":
            agent.send_output(
                agent_output_name='llm_result',
                agent_result="Error: No valid user input received (input is empty)"
            )
            return

        # 提取 Qwen 配置并校验
        api_key = os.getenv('LLM_API_KEY')
        model = os.getenv('LLM_MODEL', 'qwen-turbo')  # 默认使用 qwen-turbo
        logger.info(f"Qwen configuration - Model: {model}, API Key exists: {bool(api_key)}")
        
        # 校验 API 密钥是否存在
        if not api_key:
            agent.send_output(
                agent_output_name='llm_result',
                agent_result="Error: LLM_API_KEY not found in .env.secret (check your configuration)"
            )
            return


        # --------------------------
        # 2. 调用 Qwen API
        # --------------------------
        logger.info(f"Sending request to Qwen API (model: {model})")
        response = Generation.call(
            model=model,
            api_key=api_key,
            # Qwen 消息格式（简化版，避免部分 SDK 版本不兼容 system prompt）
            messages=[{"role": "user", "content": user_input}],
            # 显式指定参数，确保响应格式合规
            parameters={
                "temperature": 0.7,  # 控制生成文本的随机性（0~1）
                "result_format": "json"  # 强制返回 JSON 结构，避免格式混乱
            }
        )


        # --------------------------
        # 3. 解析 API 响应（多层防护 + 自适应结构）
        # --------------------------
        # 打印响应核心信息（便于调试）
        logger.info(f"Qwen API Response - Status Code: {response.status_code if hasattr(response, 'status_code') else 'Unknown'}")
        logger.info(f"Qwen API Response - Message: {response.message if hasattr(response, 'message') else 'Unknown'}")
        logger.info(f"Qwen API Response - Has Output: {hasattr(response, 'output') and response.output is not None}")

        # 初始化结果变量
        llm_result = ""

        # 第一层：校验响应是否有效
        if not response:
            llm_result = "Error: Empty response from Qwen API (check network or API status)"
        elif not hasattr(response, 'status_code'):
            llm_result = "Error: Qwen API response missing 'status_code' (invalid response structure)"
        elif response.status_code != 200:
            # HTTP 状态码非 200，提取错误原因
            error_msg = response.message if hasattr(response, 'message') else "Unknown error"
            llm_result = f"Error: Qwen API request failed (Status: {response.status_code}). Reason: {error_msg}"
        
        # 第二层：校验 output 是否存在
        elif not hasattr(response, 'output') or response.output is None:
            error_msg = response.message if hasattr(response, 'message') else "Unknown error"
            llm_result = f"Error: Qwen API has no valid 'output'. Reason: {error_msg}"
        
        # 第三层：适配不同响应结构（choices 或 text 字段）
        else:
            output = response.output
            # 打印 output 原始结构（关键调试信息）
            logger.info(f"Qwen API Output Raw Content: {vars(output)}")

            # 情况1：响应包含 choices（标准格式）
            if hasattr(output, 'choices') and output.choices is not None and len(output.choices) > 0:
                choice = output.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    llm_result = choice.message.content
                else:
                    llm_result = f"Error: Qwen 'choices' has no valid 'message.content'. Raw choices: {vars(choice)}"
            
            # 情况2：响应包含 text（简化格式，部分模型/SDK 版本返回）
            elif hasattr(output, 'text') and output.text.strip() != "":
                llm_result = output.text
            
            # 情况3：响应包含 result（兼容其他可能格式）
            elif hasattr(output, 'result') and output.result.strip() != "":
                llm_result = output.result
            
            # 情况4：output 结构未知
            else:
                llm_result = f"Error: Qwen 'output' has no valid result. Raw output: {vars(output)}"


        # --------------------------
        # 4. 输出结果到 terminal-input
        # --------------------------
        agent.send_output(
            agent_output_name='llm_result',
            agent_result=llm_result
        )
        logger.info(f"Successfully sent result to terminal: {llm_result}")


    # --------------------------
    # 全局异常捕获（避免程序崩溃）
    # --------------------------
    except Exception as e:
        error_detail = f"Runtime Error: {str(e)}"
        # 打印完整异常栈（便于定位代码问题）
        logger.error(error_detail, exc_info=True)
        # 向终端返回错误信息
        agent.send_output(
            agent_output_name='llm_result',
            agent_result=error_detail
        )


def main():
    # 初始化 MofaAgent（与 dataflow 配置中的节点名对应）
    agent = MofaAgent(agent_name='my_llm_agent')
    # 执行核心逻辑
    run(agent=agent)


if __name__ == "__main__":
    main()
