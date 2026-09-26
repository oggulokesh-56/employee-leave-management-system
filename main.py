import logging
import re
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session


from logging_info import setup_logging
logger = setup_logging()

from database import engine, Base, get_db
from models import User, Leave

EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def safe_parse_date(date_str: str):
    """Safely converts a YYYY-MM-DD string into a Python date object."""
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError, TypeError):
        return None

def calc_days(start_date_obj, end_date_obj) -> int:
    """Calculates days between two date objects safely."""
    if not start_date_obj or not end_date_obj:
        return 1
    return max((end_date_obj - start_date_obj).days + 1, 1)



@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    context = {"request": request, "error": None}
    return templates.TemplateResponse(request=request, name="login.html", context=context)


@app.post("/login", response_class=HTMLResponse)
def do_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        clean_email = email.strip()
        clean_password = password.strip()

        if not re.match(EMAIL_REGEX, clean_email):
            logger.warning(f"Invalid email format attempted: {clean_email}")
            context = {
                "request": request, 
                "error": f"'{clean_email}' is not a valid email address. Please enter a valid email."
            }
            return templates.TemplateResponse(request=request, name="login.html", context=context)

        user = db.query(User).filter(User.email == clean_email).first()

        if not user or user.password != clean_password:
            context = {"request": request, "error": "Invalid email or password."}
            return templates.TemplateResponse(request=request, name="login.html", context=context)

        if user.role == "Admin":
            return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
        else:
            return RedirectResponse(url=f"/dashboard/{user.id}", status_code=status.HTTP_302_FOUND)

    except Exception as err:
        db.rollback()
        logger.error(f"Login Error: {err}", exc_info=True)
        context = {"request": request, "error": f"Database Error: {str(err)}"}
        return templates.TemplateResponse(request=request, name="login.html", context=context)


@app.get("/logout")
def logout():
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
def user_dashboard(user_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

        my_leaves = db.query(Leave).filter(Leave.user_id == user_id).all()
        
        context = {
            "request": request,
            "user": user,
            "leave_requests": my_leaves,
            "error_msg": None
        }
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context)
    except Exception as err:
        db.rollback()
        logger.error(f"Dashboard Load Error: {err}", exc_info=True)
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.post("/apply-leave")
def apply_leave(
    request: Request,
    user_id: int = Form(...),
    leave_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        d1 = safe_parse_date(start_date)
        d2 = safe_parse_date(end_date)
        
        if not d1 or not d2:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

        total_days = calc_days(d1, d2)
        safe_reason = reason[:1000] if reason else ""

        new_leave = Leave(
            user_id=user_id,
            leave_type=leave_type,
            start_date=d1,
            end_date=d2,
            days_count=total_days,
            reason=safe_reason,
            status="Pending"
        )
        db.add(new_leave)
        db.commit()

        return RedirectResponse(url=f"/dashboard/{user_id}", status_code=status.HTTP_302_FOUND)

    except Exception as err:
        db.rollback()
        logger.error(f"Apply Leave Error: {err}", exc_info=True)
        
        user = db.query(User).filter(User.id == user_id).first()
        my_leaves = db.query(Leave).filter(Leave.user_id == user_id).all() if user else []
        
        context = {
            "request": request,
            "user": user,
            "leave_requests": my_leaves,
            "error_msg": f"Could not submit request: {str(err)}"
        }
        return templates.TemplateResponse(request=request, name="dashboard.html", context=context, status_code=400)


@app.post("/cancel-leave/{leave_id}")
def cancel_leave(leave_id: int, db: Session = Depends(get_db)):
    try:
        leave = db.query(Leave).filter(Leave.id == leave_id).first()
        if leave and leave.status == "Pending":
            uid = leave.user_id
            db.delete(leave)
            db.commit()
            return RedirectResponse(url=f"/dashboard/{uid}", status_code=status.HTTP_302_FOUND)
    except Exception as err:
        db.rollback()
        logger.error(f"Cancel Leave Error: {err}", exc_info=True)
        
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        total_users = db.query(User).filter(User.role == "Employee").count()
        all_leaves = db.query(Leave).all()
        
        pending = sum(1 for l in all_leaves if l.status == "Pending")
        approved = sum(1 for l in all_leaves if l.status == "Approved")
        rejected = sum(1 for l in all_leaves if l.status == "Rejected")

        leave_list = []
        for l in all_leaves:
            u = db.query(User).filter(User.id == l.user_id).first()
            leave_list.append({
                "id": l.id,
                "employee_name": u.name if u else "Employee",
                "leave_type": l.leave_type,
                "start_date": str(l.start_date) if l.start_date else "",
                "end_date": str(l.end_date) if l.end_date else "",
                "days_count": l.days_count,
                "reason": l.reason or "",
                "status": l.status
            })

        context = {
            "request": request,
            "manager_name": "Administrator",
            "total_employees": total_users,
            "pending_count": pending,
            "approved_count": approved,
            "rejected_count": rejected,
            "all_leave_requests": leave_list
        }
        return templates.TemplateResponse(request=request, name="admin.html", context=context)
    except Exception as err:
        db.rollback()
        logger.error(f"Admin Dashboard Error: {err}", exc_info=True)
        return HTMLResponse(f"<h2>Database Error: {str(err)}</h2>", status_code=500)


@app.post("/admin/leave/{leave_id}/approve")
def approve_leave(leave_id: int, db: Session = Depends(get_db)):
    try:
        leave = db.query(Leave).filter(Leave.id == leave_id).first()
        if leave:
            leave.status = "Approved"
            db.commit()
    except Exception as err:
        db.rollback()
        logger.error(f"Approve Leave Error: {err}", exc_info=True)
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@app.post("/admin/leave/{leave_id}/reject")
def reject_leave(leave_id: int, db: Session = Depends(get_db)):
    try:
        leave = db.query(Leave).filter(Leave.id == leave_id).first()
        if leave:
            leave.status = "Rejected"
            db.commit()
    except Exception as err:
        db.rollback()
        logger.error(f"Reject Leave Error: {err}", exc_info=True)
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@app.get("/admin/employees", response_class=HTMLResponse)
def list_employees(request: Request, db: Session = Depends(get_db)):
    try:
        employees = db.query(User).filter(User.role == "Employee").all()
        context = {
            "request": request,
            "manager_name": "Administrator",
            "employees": employees
        }
        return templates.TemplateResponse(request=request, name="employees_details.html", context=context)
    except Exception as err:
        db.rollback()
        logger.error(f"List Employees Error: {err}", exc_info=True)
        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@app.get("/admin/employees/add", response_class=HTMLResponse)
def add_employee_page(request: Request):
    context = {
        "request": request,
        "manager_name": "Administrator",
        "error": None
    }
    return templates.TemplateResponse(request=request, name="add_employee.html", context=context)


@app.post("/admin/employees/add")
def add_employee(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    job_title: str = Form(...),
    phone_number: str = Form(...),
    start_date: str = Form(...),
    status_val: str = Form(..., alias="status"),
    db: Session = Depends(get_db)
):
    try:
        clean_email = email.strip()

        if not re.match(EMAIL_REGEX, clean_email):
            context = {
                "request": request,
                "manager_name": "Administrator",
                "error": f"'{clean_email}' is not a valid email address."
            }
            return templates.TemplateResponse(request=request, name="add_employee.html", context=context)

        parsed_start_date = safe_parse_date(start_date)
        
        new_user = User(
            name=name.strip(),
            email=clean_email,
            password="password123",
            job_title=job_title.strip()[:100],
            phone=phone_number.strip()[:50],
            start_date=parsed_start_date,
            role="Employee",
            status=status_val
        )
        db.add(new_user)
        db.commit()
        return RedirectResponse(url="/admin/employees", status_code=status.HTTP_302_FOUND)

    except Exception as err:
        db.rollback()
        logger.error(f"Add Employee Error: {err}", exc_info=True)
        context = {
            "request": request,
            "manager_name": "Administrator",
            "error": "Failed to create employee. Email may already exist or dates are invalid."
        }
        return templates.TemplateResponse(request=request, name="add_employee.html", context=context)


@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception on {request.url.path}: {exc}", exc_info=True)
    return HTMLResponse(  
        content=f"""
        <div style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h2 style="color: #dc3545;">Server Error</h2>
            <p><strong>Route:</strong> {request.url.path}</p>
            <p><strong>Error Message:</strong> {str(exc)}</p>
            <a href="/" style="padding: 10px 20px; background-color: #0d6efd; color: white; text-decoration: none; border-radius: 5px;">Return to Home</a>
        </div>
        """,
        status_code=500
    )