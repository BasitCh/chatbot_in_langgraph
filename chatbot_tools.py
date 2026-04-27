from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool

@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
  """
  perform basic arithmatic opertion on two number.
  supported operation: add, mul, sub, div
  """
  try:
    match operation:
      case 'add':
        result = first_num + second_num
      case 'sub':
        result = first_num - second_num
      case 'div':
        if second_num == 0:
          return {'error': 'Division by zero is not allowed'}
        else:
          result = first_num / second_num
      case 'mul':
        result = first_num * second_num
      case _:
        return {'error': f"Unsupported operation {operation}"}

    return {'First Number': first_num, 'Second Number': second_num, 'Result': result}
  except Exception as e:
    return {'error': str(e)}


@tool
def search_linkedin_jobs(job_title: str, location: str):
  """
  Search for active and latest job posts on linkedIn also search post where people are talking about flutter
  input should be job title and location
  """
  optimized_query = f"site:linkedin.com/jobs/view '{job_title}' in {location}"
  results = TavilySearchResults(max_results=5).invoke(optimized_query)
  return results


class ChatbotTools:
  def __init__(self):
    self.search_tool = TavilySearchResults(max_results=5)

  def getTools(self):
    return [self.search_tool, calculator, search_linkedin_jobs]