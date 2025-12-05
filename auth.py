from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client
from utils.supabase_client import get_supabase

# Define the security scheme (Bearer Token)
security = HTTPBearer()

class UserContext:
    """
    Holds the context of the authenticated user.
    This is injected into API routes so we know who is making the request.
    """
    def __init__(self, user_id: str, email: str, tenant_id: str, role: str):
        self.user_id = user_id
        self.email = email
        self.tenant_id = tenant_id
        self.role = role

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_supabase)
) -> UserContext:
    """
    Dependency that verifies the JWT token and retrieves the user's context (Tenant ID).
    """
    token = credentials.credentials
    
    try:
        # 1. Verify Token with Supabase Auth
        # getUser() verifies the token signature and expiration automatically
        user_response = supabase.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        user = user_response.user
        user_id = user.id
        email = user.email

        # 2. Fetch Profile to get Tenant ID
        # We query the 'profiles' table we created in setup_db.sql
        profile_res = supabase.table("profiles").select("tenant_id, role").eq("id", user_id).single().execute()
        
        if not profile_res.data:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User profile not found. Please contact support.",
            )
            
        profile = profile_res.data
        tenant_id = profile.get("tenant_id")
        role = profile.get("role", "member")

        if not tenant_id:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not assigned to a tenant/organization.",
            )

        return UserContext(
            user_id=user_id,
            email=email,
            tenant_id=tenant_id,
            role=role
        )

    except Exception as e:
        print(f"Auth Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
