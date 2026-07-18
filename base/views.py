import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .matcher import get_best_answer, QUESTIONS


def chat_view(request):
    """Renders the chat page. Passes a few sample questions to show as quick-start chips."""
    sample_questions = QUESTIONS[:4]
    return render(request, "base/home.html", {"sample_questions": sample_questions})


@require_POST
def ask_view(request):
    """AJAX endpoint: receives {"question": "..."} and returns {"answer": "..."}."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)

    question = (data.get("question") or "").strip()
    if not question:
        return JsonResponse({"error": "Question is empty."}, status=400)

    result = get_best_answer(question)
    return JsonResponse(result)
