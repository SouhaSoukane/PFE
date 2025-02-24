from fastapi import APIRouter, HTTPException, Depends
from database import get_salesforce_session, get_sf


from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
router = APIRouter()

@router.get("/")
def root():
    return {"message": "Salesforce API is ready"}

def refresh_salesforce():
    """Rafraîchir la connexion Salesforce en cas d'erreur d'authentification."""
    global sf, access_token, instance_url
    access_token, instance_url = get_salesforce_session()
    sf = Salesforce(instance_url=instance_url, session_id=access_token)


@router.get("/accounts/")
def get_accounts(sf=Depends(get_sf)):
    """Récupérer tous les comptes Salesforce."""
    query = "SELECT Id FROM Warehouse__c "
    try:
        result = sf.query(query)
        return result["records"]
    except SalesforceAuthenticationFailed:
        refresh_salesforce()
        try:
            result = sf.query(query)
            return result["records"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

