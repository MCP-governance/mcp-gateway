import time
import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from services import shared

def request(token):
    return Request({"type":"http","headers":[(b"authorization",("Bearer "+token).encode())]})

@pytest.mark.asyncio
async def test_signed_expired_token_and_admin_roles(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    class Keys:
        def get_signing_key_from_jwt(self,token):
            return type("Signing",(),{"key":key.public_key()})()
    monkeypatch.setenv("OIDC_ISSUER","test-issuer");monkeypatch.setenv("OIDC_JWKS_URL","unused")
    monkeypatch.setattr(shared,"jwks_client",lambda url:Keys())
    claims={"sub":"user","iss":"test-issuer","aud":"mcp-gateway","iat":int(time.time()),"exp":int(time.time())+60,"realm_access":{"roles":["user"]}}
    token=jwt.encode(claims,key,algorithm="RS256")
    assert (await shared.authenticate(request(token)))["sub"]=="user"
    with pytest.raises(HTTPException) as e: await shared.authenticate(request(token),admin=True)
    assert e.value.status_code==403
    claims["exp"]=int(time.time())-1
    with pytest.raises(HTTPException) as e: await shared.authenticate(request(jwt.encode(claims,key,algorithm="RS256")))
    assert e.value.status_code==401
