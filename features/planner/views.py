import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from features.accounts.models import UserProfile, is_management, user_role
from features.tasks.services import notify_management, notify_user
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
    leave_start_date, leave_end_date, leave_end_exclusive = selected_leave_range(request, start_date, end_date)
    leave_summary = leave_days_summary(request.user, leave_start_date, leave_end_exclusive)

    if request.method == 'POST' and request.POST.get('form') == 'leave_request':
        if user_role(request.user) == UserProfile.Role.CLIENT:
            return redirect('calendar')
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.user = request.user
            leave_request.save()
            notify_management(
                'Nowy wniosek o wolne',
                f'{request.user.get_full_name() or request.user.username}: {leave_request.start_date:%Y-%m-%d} - {leave_request.end_date:%Y-%m-%d}',
                kind='leave',
                url=f"{reverse('calendar')}?month={leave_request.start_date:%Y-%m}",
                actor=request.user,
            )
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
        'today': timezone.localdate(),
        'weeks': build_calendar_days(request.user, month_date, start_date, end_date),
        'leave_form': form,
        'leave_requests': sorted_leave_requests(leave_request_list_queryset(request.user, leave_start_date, leave_end_exclusive)),
        'leave_summary': leave_summary,
        'leave_date_from': leave_start_date.isoformat(),
        'leave_date_to': leave_end_date.isoformat(),
        'leave_period_label': f'{leave_start_date:%Y-%m-%d} - {leave_end_date:%Y-%m-%d}',
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
    status_label = 'zaakceptowany' if status == LeaveRequest.Status.APPROVED else 'odrzucony'
    notify_user(
        leave_request.user,
        'Status wniosku o wolne',
        f'Twój wniosek {leave_request.start_date:%Y-%m-%d} - {leave_request.end_date:%Y-%m-%d} został {status_label}.',
        kind='leave',
        url=f"{reverse('calendar')}?month={leave_request.start_date:%Y-%m}",
        actor=request.user,
    )
    messages.success(request, 'Status wniosku został zaktualizowany.')
    return redirect(request.POST.get('next') or 'calendar')


@login_required
@require_POST
def mark_leave_as_read(request, leave_id):
    leave_request = get_object_or_404(LeaveRequest, pk=leave_id, user=request.user)
    if leave_request.status != LeaveRequest.Status.REJECTED:
        return redirect(request.POST.get('next') or 'calendar')

    leave_request.mark_as_read()
    messages.success(request, 'Wniosek został oznaczony jako przeczytany.')
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


def selected_leave_range(request, default_start, default_end):
    start_date = default_start
    end_date = default_end - timedelta(days=1)

    raw_start = request.GET.get('date_from')
    raw_end = request.GET.get('date_to')
    if raw_start:
        try:
            start_date = date.fromisoformat(raw_start)
        except ValueError:
            pass
    if raw_end:
        try:
            parsed_end = date.fromisoformat(raw_end)
            if parsed_end >= start_date:
                end_date = parsed_end
        except ValueError:
            pass

    return start_date, end_date, end_date + timedelta(days=1)


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
                'has_approved_leave': any(leave.status == LeaveRequest.Status.APPROVED and leave.user_id == user.id for leave in day_leaves),
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
    requests = leave_request_calendar_queryset(user, start_date, end_date)
    leave_by_day = defaultdict(list)
    for leave_request in requests:
        current = max(leave_request.start_date, start_date)
        last_day = min(leave_request.end_date, end_date - timedelta(days=1))
        while current <= last_day:
            leave_by_day[current].append(leave_request)
            current += timedelta(days=1)
    return leave_by_day


def leave_request_base_queryset(start_date, end_date):
    return LeaveRequest.objects.select_related('user', 'reviewed_by').filter(
        start_date__lt=end_date,
        end_date__gte=start_date,
    )


def leave_request_calendar_queryset(user, start_date, end_date):
    qs = leave_request_base_queryset(start_date, end_date)
    if is_management(user):
        return qs
    return qs.filter(user=user).exclude(
        status=LeaveRequest.Status.REJECTED,
        read_at__isnull=False,
    )


def leave_request_list_queryset(user, start_date, end_date):
    qs = leave_request_base_queryset(start_date, end_date)
    if is_management(user):
        return qs
    return qs.filter(user=user).exclude(
        status=LeaveRequest.Status.REJECTED,
        read_at__isnull=False,
    )


def leave_days_summary(user, month_start, month_end):
    qs = leave_request_base_queryset(month_start, month_end).filter(status=LeaveRequest.Status.APPROVED)
    if not is_management(user):
        qs = qs.filter(user=user)

    requests = list(qs)
    summary = {
        'month_days': working_days_count(requests, month_start, month_end),
        'is_management': is_management(user),
        'employees': [],
    }

    if is_management(user):
        employees = User.objects.filter(profile__role=UserProfile.Role.EMPLOYEE).order_by('first_name', 'last_name', 'username')
        for employee in employees:
            employee_requests = [item for item in requests if item.user_id == employee.id]
            month_days = working_days_count(employee_requests, month_start, month_end)
            if month_days:
                summary['employees'].append({
                    'user': employee,
                    'month_days': month_days,
                })

    return summary


def working_days_count(leave_requests, period_start, period_end):
    dates = set()
    for leave_request in leave_requests:
        dates.update(working_days_in_range(leave_request, period_start, period_end))
    return len(dates)


def working_days_in_range(leave_request, period_start, period_end):
    current = max(leave_request.start_date, period_start)
    last_day = min(leave_request.end_date, period_end - timedelta(days=1))
    dates = set()
    while current <= last_day:
        if current.weekday() < 5:
            dates.add(current)
        current += timedelta(days=1)
    return dates


def sorted_leave_requests(requests):
    today = timezone.localdate()
    return sorted(
        requests,
        key=lambda leave_request: (
            leave_request.start_date < today,
            leave_request.start_date if leave_request.start_date >= today else -leave_request.start_date.toordinal(),
        ),
    )
