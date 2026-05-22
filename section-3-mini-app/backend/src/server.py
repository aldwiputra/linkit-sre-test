"""Entry point"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()

if __name__ == "__main__":
    print("🚀 LINKIT SRE Backend running on http://localhost:5000")
    app.run(host="0.0.0.0", port=8383, debug=False)
