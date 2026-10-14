"""캐시·저장 모델 추론 중 DNS와 소켓 송신을 차단하고 시도 횟수만 기록한다."""
from contextlib import contextmanager
import socket


class NetworkAccessBlocked(RuntimeError):
    pass


@contextmanager
def deny_network():
    """한 프로세스의 동기 추론 검증용. 완전한 OS 격리나 일반 보안 경계를 주장하지 않는다."""
    attempts = []; originals = []
    for owner, name in [(socket, 'create_connection'), (socket, 'getaddrinfo'),
                        (socket.socket, 'connect'), (socket.socket, 'connect_ex'), (socket.socket, 'sendto')]:
        original = getattr(owner, name); originals.append((owner, name, original))
        def blocked(*args, operation=name, **kwargs):
            # 주소·URL·인증값·호출 인자는 저장하지 않는다.
            attempts.append(operation)
            raise NetworkAccessBlocked('Local inference cannot use network: '+operation)
        setattr(owner, name, blocked)
    try:
        yield attempts
    finally:
        for owner, name, original in originals:
            setattr(owner, name, original)
