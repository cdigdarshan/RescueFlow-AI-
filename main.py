import argparse
from pathlib import Path

from app.config import DEFAULT_VIDEO


def parse_args():
    parser = argparse.ArgumentParser(description="Vehicle detection and traffic optimization dashboard")
    parser.add_argument(
        "-p",
        "--path",
        default=str(DEFAULT_VIDEO),
        help="Path to an MP4 traffic video. Defaults to assets/videos/traffic_video.mp4.",
    )
    parser.add_argument("-l", "--live", action="store_true", help="Use the webcam as the video source.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the Flask app.")
    parser.add_argument("--port", default=5000, type=int, help="Port for the Flask app.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    from app.routes import create_app

    source = "webcam" if args.live else Path(args.path)
    app = create_app(source)
    app.run(host=args.host, port=args.port, threaded=True)
