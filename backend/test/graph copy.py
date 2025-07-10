import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

load_dotenv()
llm = ChatOpenAI(
    model="openai/gpt-4o-mini",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0,    
)
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What is the capital of France?"),
    AIMessage(content="The capital of France is Paris.", name="WIKIPEDIA"),
    HumanMessage(content="Can you see the name of the source of your previous response?"),
]
message = llm.invoke(messages)
print(message)
