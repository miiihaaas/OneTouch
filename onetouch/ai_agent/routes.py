from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from onetouch.ai_agent.agent import process_chat_message

ai_agent = Blueprint('ai_agent', __name__)

@ai_agent.route('/api/ai/chat', methods=['POST'])
@login_required
def chat():
    if current_user.user_role != 'admin':
        return jsonify({
            "success": False,
            "message": "Niste autorizovani da koristite AI agenta"
        })
    user_message = request.json.get('message')
    
    # AI agent ima pristup current_user contextu
    response = process_chat_message(
        message=user_message,
        user=current_user
    )
    
    return jsonify(response)