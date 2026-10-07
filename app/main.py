from app.web import web_app

# Existing LangGraph workflow remains the application core.
# This module is now the Flask entry point.
if __name__ == "__main__":
    web_app.run(debug=True)
