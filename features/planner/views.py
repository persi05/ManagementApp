import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, is_management, user_role
from features.tasks.selectors import visible_tasks
from features.time_tracking.models import TimeEntry

from .forms import LeaveRequestForm
from .models import LeaveRequest


POLISH_MONTHS = {
    1: 'Styczeń',
    2: 'Luty',
    3: 'Marzec',
    4: 'Kwiecień',
    5: 'Maj',
    6: 'Czerwiec',
    7: 'Lipiec',
    8: 'Sierpień',
    9: 'Wrzesień',
    10: 'Październik',
    11: 'Listopad',
    12: 'Grudzień',
}


@login_required
def calendar_view(request):
    month_date = selected_month(request)
    start_date, end_date = month_range(month_date)

    if request.method == 'POST' and request.POST.get('form') == 'leave_request':
        if user_role(request.user) == UserProfile.Role.CLIENT:
            return redirect('calendar')
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.user = request.user
            leave_request.save()
            messages.success(request, 'Wniosek o wolne został wysłany.')
            return redirect(f'{request.path}?month={month_date:%Y-%m}')
    else:
        form = LeaveRequestForm()

    context = {
        'month': month_date.strftime('%Y-%m'),
        'month_name': POLISH_MONTHS[month_date.month].upper(),
        'month_label': f'{POLISH_MONTHS[month_date.month]} {month_date.year}',
        'previous_month': add_months(month_date, -1).strftime('%Y-%m'),
        'next_month': add_months(month_date, 1).strftime('%Y-%m'),
        'weekdays': ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd'],
        'weeks': build_calendar_days(request.user, month_date, start_date, end_date),
        'leave_form': form,
        'leave_requests': leave_request_queryset(request.user, start_date, end_date),
        'can_request_leave': user_role(request.user) != UserProfile.Role.CLIENT,
        'can_review_leave': is_management(request.user),
        'is_management_view': is_management(request.user),
        'is_client_view': user_role(request.user) == UserProfile.Role.CLIENT,
    }
    return render(request, 'features/calendar.html', context)


@login_required
@require_POST
def update_leave_status(request, leave_id):
    if not is_management(request.user):
        return redirect('calendar')

    status = request.POST.get('status')
    if status not in {LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED}:
        return redirect('calendar')

    leave_request = get_object_or_404(LeaveRequest, pk=leave_id)
    leave_request.set_status(status, request.user)
    messages.success(request, 'Status wniosku został zaktualizowany.')
    return redirect(request.POST.get('next') or 'calendar')


def selected_month(request):
    raw_month = request.GET.get('month')
    if raw_month:
        try:
            return date.fromisoformat(f'{raw_month}-01')
        except ValueError:
            pass
    today = timezone.localdate()
    return today.replace(day=1)


def month_range(month_date):
    start_date = month_date.replace(day=1)
    end_date = add_months(start_date, 1)
    return start_date, end_date


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def build_calendar_days(user, month_date, start_date, end_date):
    time_by_day, people_by_day = time_summary_by_day(user, start_date, end_date)
    tasks_by_day = tasks_due_by_day(user, start_date, end_date)
    leave_by_day = leave_by_day_for_user(user, start_date, end_date)
    month_calendar = calendar.Calendar(firstweekday=0)
    weeks = []

    for week in month_calendar.monthdatescalendar(month_date.year, month_date.month):
        week_days = []
        for day in week:
            day_tasks = tasks_by_day.get(day, [])
            day_leaves = leave_by_day.get(day, [])
            day_people = people_by_day.get(day, [])
            hours = time_by_day.get(day, Decimal('0'))
            week_days.append({
                'date': day,
                'in_month': day.month == month_date.month,
                'is_today': day == timezone.localdate(),
                'hours': hours,
                'tasks': day_tasks,
                'people': day_people,
                'leaves': day_leaves,
                'has_work': bool(hours),
                'has_tasks': bool(day_tasks),
                'has_leave': bool(day_leaves),
            })
        weeks.append(week_days)

    return weeks


def time_summary_by_day(user, start_date, end_date):
    entries = TimeEntry.objects.select_related('user').filter(start__date__gte=start_date, start__date__lt=end_date)
    if not is_management(user):
        entries = entries.filter(user=user)

    time_by_day = defaultdict(lambda: Decimal('0'))
    people_nested = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
    for entry in entries:
        day = timezone.localtime(entry.start).date()
        hours = entry.hours
        time_by_day[day] += hours
        people_nested[day][entry.user] += hours

    people_by_day = {
        day: [{'user': person, 'hours': hours} for person, hours in people.items()]
        for day, people in people_nested.items()
    }
    return time_by_day, people_by_day


def tasks_due_by_day(user, start_date, end_date):
    tasks = visible_tasks(user).filter(due_date__gte=start_date, due_date__lt=end_date).select_related('project', 'assignee', 'column')
    tasks_by_day = defaultdict(list)
    for task in tasks:
        tasks_by_day[task.due_date].append(task)
    return tasks_by_day


def leave_by_day_for_user(user, start_date, end_date):
    requests = leave_request_queryset(user, start_date, end_date)
    leave_by_day = defaultdict(list)
    for leave_request in requests:
        current = max(leave_request.start_date, start_date)
        last_day = min(leave_request.end_date, end_date - timedelta(days=1))
        while current <= last_day:
            leave_by_day[current].append(leave_request)
            current += timedelta(days=1)
    return leave_by_day


def leave_request_queryset(user, start_date, end_date):
    qs = LeaveRequest.objects.select_related('user', 'reviewed_by').filter(
        start_date__lt=end_date,
        end_date__gte=start_date,
    )
    if is_management(user):
        return qs
    return qs.filter(user=user)
