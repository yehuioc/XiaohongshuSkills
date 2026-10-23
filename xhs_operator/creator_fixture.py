"""Fixed, generated test media only; no arbitrary file upload interface."""
import base64
import hashlib
import json

from .store import PROJECT, Problem

TITLE = '测试勿发布·功能调研'
BODY = '这是创作者平台功能调研的独立测试稿，不用于正式发布。\n\n本轮仅检查标题、正文、媒体上传、封面预览和内容设置。素材由本项目自行生成，不含个人资料，不引用真实用户经历。\n\n检查结束后保留测试稿，供人工核对。请勿将本条测试稿发布。'


def fixture_args(fixture):
    if fixture not in ('image', 'video', 'audio', 'longform'):
        raise Problem('仅允许项目自制的固定调研素材')
    args = {'fixture': fixture, 'title': TITLE, 'body': BODY}
    if fixture == 'longform':
        return args
    root = PROJECT / 'data/operator/diagnostics/creator-research/fixtures'
    if not root.resolve().is_relative_to(PROJECT.resolve()):
        raise Problem('测试素材目录不在本项目内')
    expected = {'image': ('creator-test.png', 'image/png'), 'video': ('creator-test.mp4', 'video/mp4'), 'audio': ('creator-test.mp3', 'audio/mpeg')}
    name, mime = expected[fixture]
    if not (root / 'manifest.json').is_file():
        raise Problem('尚未生成测试素材；请先安装 requirements-dev.txt，再运行 python scripts/create_creator_test_fixtures.py')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))[fixture]
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise Problem('测试素材文件不在固定目录内')
    data = path.read_bytes()
    if manifest.get('name') != name or manifest.get('mime') != mime or hashlib.sha256(data).hexdigest() != manifest.get('sha256') or len(data) > 4_500_000:
        raise Problem('调研素材与固定清单不一致或过大，未上传')
    return args | {'name': name, 'mime': mime, 'sha256': manifest['sha256'], 'data': base64.b64encode(data).decode()}
