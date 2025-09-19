from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
)
from src.utils.logger import logger
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.api.models.knowledge_model import Website
from src.api.models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import WebKnowledgeSchema
from src.api.security.auth import get_api_key, API_KEY
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)

router = APIRouter(
    prefix="/workspace/web_knowledge",
    tags=["WebKnowledge"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
def get_status():
    return success(data={"status": "Web Knowledge Route is operational"})

# get knowledes
@router.get("/all")
def get_web_knowledges(
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info("Fetching all web knowledges")
        print(request)
        web_knowledges = db.query(Website).all()
        return success(data=[knowledge.to_dict() for knowledge in web_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    

# Get knowledge by ID
@router.get("/{web_id}")
def get_web_knowledge(
        web_id: str,
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Fetching knowledge with ID: {web_id}")
        knowledge = db.query(Website).filter(Website.id == web_id).first()
        if not knowledge:
            raise ResourceNotFoundException(f"Knowledge with ID {web_id} not found")
        return success(data=knowledge.to_dict())
    except ResourceNotFoundException as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# Add new knowledge
@router.post("/add")
async def add_web_knowledge(
        data:WebKnowledgeSchema,
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
        if api_key != API_KEY:
            raise WrextAuthenticationException(
                message="Invalid API key provided",
                context={"api_key_provided": bool(api_key)}
            )
        try:
            logger.info("Check the workspace exists")
            workspace = db.query(WorkspaceModel).filter(WorkspaceModel.id == data.workspace_id).first()
            if not workspace:
                raise ResourceNotFoundException(f"Workspace with ID {data.workspace_id} not found")
            
            # check if the knowledge already exists
            existing_knowledge = db.query(Website).filter(Website.url == str(data.url), Website.workspace_id == str(data.workspace_id)).first()
            if existing_knowledge:
                raise DuplicateResourceException(f"Knowledge for URL {data.url} already exists in the workspace")


            logger.info(f"Scraping content from URL: {data.url}")
            chunks, results = await web_page_scraper(urls=[data.url])
            result = results[0]
            if not result.success:
                logger.error(f"Failed to scrape URL: {str(data.url)}")
                raise WrextValidationException(
                    message="Failed to scrape the provided URL",
                    field_errors={"url": ["URL could not be scraped or is inaccessible"]}
                )

            logger.info(f"Building vector store for the scraped content")
            # Push scraped chunks into vector store
            logger.info(f"Saving knowledge entry to the database")
            new_knowledge = Website(
                workspace_id=data.workspace_id,
                url=result.url,
                status="trained",
                char_count=len(result.markdown),
                word_count=len(result.markdown.split()) if result else 0
            )
            db.add(new_knowledge)
            db.commit()
            db.refresh(new_knowledge)

            try:
                logger.info(f"Inserting {len(chunks)} chunks into vector store for {result.url}")
                success_status = add_to_vector_store(blog_context=chunks,
                                                     doc_id=f"{str(workspace.id)}_{str(new_knowledge.id)}")
                if not success_status:
                    raise WrextExternalServiceException(
                        message="Failed to insert chunks into vector store",
                        service_name="vector_store",
                        service_error="Insertion returned False"
                    )
            except Exception as vec_err:
                logger.exception("Vector store insertion failed")
                raise WrextExternalServiceException(
                    message="Failed to process content in vector store",
                    service_name="vector_store",
                    service_error=str(vec_err)
                )

            knowledge_data = {
                "web_id": str(new_knowledge.id),
                "url": new_knowledge.url,
                "status": new_knowledge.status,
                "char_count": new_knowledge.char_count,
                "word_count": new_knowledge.word_count,
            }

            logger.info(f"Knowledge entry created with ID: {new_knowledge.id}")
            return created(
                data={"knowledge": knowledge_data},
                request=request,
                message="Web knowledge added and processed successfully"
            )

        except DuplicateResourceException as e:
            logger.warning(str(e))
            raise HTTPException(status_code=409, detail=str(e))
        except WrextValidationException as e:
            logger.warning(str(e))
            raise HTTPException(status_code=400, detail=str(e))
        except WrextExternalServiceException as e:
            logger.error(str(e))
            raise HTTPException(status_code=502, detail="External Service Error")
        except Exception as e:
            logger.error(f"Error adding knowledge: {e}")
            raise HTTPException(status_code=500, detail="Internal Server Error")
        
# Delete knowledge by ID
@router.delete("/delete/{workspace_id}/{web_id}")
def delete_web_knowledge(
        workspace_id: str,
        web_id: str,
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Deleting knowledge with ID: {web_id} from workspace: {workspace_id}")
        knowledge = db.query(Website).filter(Website.id == web_id, Website.workspace_id == workspace_id).first()
        if not knowledge:
            raise ResourceNotFoundException(f"Knowledge with ID {web_id} not found in the specified workspace")

        # delete vector from store
        success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(web_id)}")
        if not success_status:
            return error(
                message="Failed to delete vector store",
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                status_code=500,
                severity=ErrorSeverity.HIGH,
                context={"workspace_id": workspace_id, "error_details": "Unable to delete vectors"},
                request=request
            )
        
        db.delete(knowledge)
        db.commit()
        logger.info(f"Knowledge with ID: {web_id} deleted successfully")
        return success(
            data={},
            request=request,
            message="Knowledge deleted successfully"
        )
    except ResourceNotFoundException as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")