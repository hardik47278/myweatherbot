import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field 
from typing import Annotated, List, Dict
from typing_extensions import TypedDict
from langchain_groq import ChatGroq
from langgraph.graph.message import add_messages
from langgraph.graph import START, StateGraph, END
from langgraph.constants import Send
import operator
import langserve as ls

# Load environment variables
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# Initialize LLM
llm = ChatGroq(model="Gemma2-9b-It", temperature=0.7)

# Define the structured output schema
class Section(BaseModel):
    name: str
    description: str

class Sections(BaseModel):
    sections: List[Section]

# Planner to add structured output to LLM
planner = llm.with_structured_output(Sections)

# State definitions for processing the question
class State(TypedDict):
    topic: str
    sections: List[Dict]
    completed_sections: Annotated[List, operator.add]
    final_report: str

class WorkerState(TypedDict):
    section: Dict
    completed_sections: Annotated[List, operator.add]

# Define teacher node logic
def teacher_node(role: str):
    def teacher(state: WorkerState):
        section = llm.invoke([
            SystemMessage(content=f"You are a {role} teacher. Provide a clear and comprehensive explanation using markdown formatting."),
            HumanMessage(content=f"Query details: {state['section']['description']}")
        ])
        return {"completed_sections": [section.content], "section": state["section"]}
    return teacher

# Feedback node logic
def student_feedback(state: WorkerState):
    teacher_response = state["completed_sections"][-1]
    feedback = state.get("feedback", "")
    if feedback.strip():
        improved = llm.invoke([
            SystemMessage(content="You are an AI teacher tasked with refining your explanation based on student feedback."),
            HumanMessage(content=f"Feedback: {feedback}\nPrevious Answer: {teacher_response}")
        ])
        return {"completed_sections": [improved.content], "section": state["section"]}
    else:
        return {"completed_sections": [teacher_response], "section": state["section"]}

# Orchestrator logic to assign teachers based on query
def orchestrator(state: State):
    report_sections = planner.invoke([
        SystemMessage(content="Decide which teacher should be assigned to answer the following subject query. The available teachers are for Math, Physics, Chemistry, and Science."),
        HumanMessage(content=f"Subject query: {state['topic']}")
    ])
    if not report_sections or not report_sections.sections:
        raise ValueError("No sections were generated for the query.")
    sections_list = [section.model_dump() for section in report_sections.sections]
    return {"sections": sections_list}

# Synthesizer logic to combine all teacher responses into final answer
def synthesizer(state: State):
    final_report = "\n\n---\n\n".join(state["completed_sections"])
    return {"final_report": final_report}

# Build the LangServe app
def q_and_a_manager():
    builder = StateGraph(State)
    builder.add_node("orchestrator", orchestrator)
    builder.add_node("math_teacher", teacher_node("Math"))
    builder.add_node("physics_teacher", teacher_node("Physics"))
    builder.add_node("chemistry_teacher", teacher_node("Chemistry"))
    builder.add_node("science_teacher", teacher_node("Science"))
    builder.add_node("student_feedback", student_feedback)
    builder.add_node("synthesizer", synthesizer)

    def assign_teacher(state: State):
        worker_mapping = {
            "Math": "math_teacher",
            "Physics": "physics_teacher",
            "Chemistry": "chemistry_teacher",
            "Science": "science_teacher"
        }
        return [Send(worker_mapping.get(s["name"], "science_teacher"), {"section": s}) for s in state["sections"]]

    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges("orchestrator", assign_teacher, ["math_teacher", "physics_teacher", "chemistry_teacher", "science_teacher"])
    builder.add_edge("math_teacher", "student_feedback")
    builder.add_edge("physics_teacher", "student_feedback")
    builder.add_edge("chemistry_teacher", "student_feedback")
    builder.add_edge("science_teacher", "student_feedback")
    builder.add_edge("student_feedback", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile()

# Initialize the agent
agent = q_and_a_manager()

# Define the LangServe endpoint
@ls.app.post("/query")
async def query_subject(state: State):
    try:
        result = agent.invoke(state)
        return result
    except Exception as e:
        return {"error": str(e)}

# Define entry point for LangServe deployment
if __name__ == "__main__":
    ls.app.run()
