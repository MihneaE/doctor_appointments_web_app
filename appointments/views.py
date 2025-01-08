from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.decorators import login_required
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.conf import settings
from django.contrib.auth import logout
from .forms import ProfilePictureForm
from .models import Doctor
from .models import MedicalSpecialty
from .models import Client
from .models import Comment
from .models import Slot
from .models import Appointment
from django.shortcuts import get_object_or_404
from django.http import HttpResponseBadRequest
from datetime import datetime, timedelta
from django.http import JsonResponse
import json
import pdb
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
import calendar
from itsdangerous import URLSafeTimedSerializer
from django.utils.timezone import now
from django.utils import timezone
from rest_framework.viewsets import ModelViewSet
from .serializers import MedicalSpecialtySerializer
from .celery_tasks import process_data
from django.http import HttpResponseNotAllowed

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

class MedicalSpecialtyViewSet(ModelViewSet):
    queryset = MedicalSpecialty.objects.all()
    serializer_class = MedicalSpecialtySerializer

def exemple_celery_function_process_data_view(request):
    if request.method == "POST":
        task_result = process_data.delay("Hello World!")
        return JsonResponse({"message": "Task has been queued", "task_id": task_result.id})
    
    return render(request, 'appointments/test_celery.html')

def home(request):
    query = request.GET.get('q')

    if query:
        medical_specialties = MedicalSpecialty.objects.filter(name__icontains=query)
    else:
        medical_specialties = MedicalSpecialty.objects.all()

    total_specialties = MedicalSpecialty.objects.count()
    total_doctors = Doctor.objects.count()
    total_appointments = Appointment.objects.count()
    total_users = User.objects.count()

    return render(request, 'appointments/home.html', {
        'medical_specialties': medical_specialties,
        'total_specialties': total_specialties,
        'total_doctors': total_doctors,
        'total_appointments': total_appointments,
        'total_users': total_users,
    }, )

def specialty_details(request, specialty_name):
    query = request.GET.get('q')

    doctors = Doctor.objects.filter(specialization__iexact=specialty_name)

    if query:
        doctors = doctors.filter(user__username__icontains=query)

    gender = request.GET.get('gender')
    if gender in ['male', 'female']:
        doctors = doctors.filter(gender__iexact=gender)

    experience = request.GET.get('experience')

    if experience:
        try:
            experience = int(experience)
            doctors = doctors.filter(experience__gte=experience)
        except ValueError:
            pass

    fee = request.GET.get('fee')
    if fee == 'low':
        doctors = doctors.filter(consultation_fee__lt=500)
    elif fee == 'medium':
        doctors = doctors.filter(consultation_fee__gte=500, consultation_fee__lte=1000)
    elif fee == 'high':
        doctors = doctors.filter(consultation_fee__gt=1000)

    sort = request.GET.get('sort')
    if sort == 'fee-low':
        doctors = doctors.order_by('consultation_fee')
    elif sort == 'fee-high':
        doctors = doctors.order_by('-consultation_fee')

    return render(request, 'appointments/doctors_page.html', {'specialty_name': specialty_name, 'doctors': doctors})

@login_required
def add_comment(request, doctor_username):
    if request.method == 'POST':
        doctor = get_object_or_404(Doctor, user__username=doctor_username)
        user_photo = request.user.profile_picture.url if hasattr(request.user, 'profile_picture') else None
        content = request.POST.get('content')
        rating = request.POST.get('rating')

        Comment.objects.create (
            doctor=doctor,
            user=request.user,
            user_photo=user_photo,
            rating=rating,
            content=content,
        )

        return redirect('view_doctor_profile_by_cli', username=doctor_username)

@login_required
def update_profile_picture(request):
    profile, created = Doctor.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        print("POST request received")
        form = ProfilePictureForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            print("Form is valid")
            form.save()
            print("Profile photo updated")

            if request.user.groups.filter(name='Doctor').exists():
                return redirect('doctor_profile')
            elif request.user.groups.filter(name='Client').exists():
                return redirect('client_profile')
            
        else:
            print("Form is invalid")
    else:
        form = ProfilePictureForm(instance=profile)

@login_required
def update_client_profile(request):
    try:
        client = request.user.client_profile  
    except Client.DoesNotExist:
        messages.error(request, "Client profile not found.")
        return redirect('client_profile')  

    if request.method == 'POST':
        username = request.POST.get('username')
        real_name = request.POST.get('real_name')
        email = request.POST.get('email')
        contact = request.POST.get('contact')
        address = request.POST.get('address')
        date_of_birth = request.POST.get("date_of_birth")
        gender = request.POST.get("gender")

        user = client.user
        user.username = username
        user.real_name = real_name
        user.email = email
        user.save()

        client.user.username = username
        client.user.real_name = real_name
        client.user.email = email
        client.contact = contact
        client.address = address
        client.gender = gender

        if date_of_birth: 
            try:
                client.date_of_birth = date_of_birth  
            except ValidationError:
                messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
                return render(request, 'appointments/client_profile.html', {"client": client})
        else:
            client.date_of_birth = None 

        client.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('client_profile') 

@login_required
def update_doctor_profile_proffessional(request):
    try:
        doctor = request.user.doctor_profile  
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    if request.method == 'POST':
        specialization = request.POST.get('specialization')
        qualification = request.POST.get('qualification')
        experience = request.POST.get('experience')
        certifications = request.POST.get('certifications')
        professional_description = request.POST.get('professional_description')

        doctor.specialization = specialization
        doctor.qualification = qualification
        doctor.experience = experience
        doctor.certifications = certifications
        doctor.professional_description = professional_description

        doctor.save()
        messages.success(request, "Professional details updated successfully!")
        return redirect('doctor_profile') 

@login_required
def update_doctor_profile_work(request):
    try:
        
        doctor = request.user.doctor_profile  
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    if request.method == 'POST':
        clinic_hospital = request.POST.get('clinic_hospital')
        address = request.POST.get('address')
        availability = request.POST.get('availability')
        services = request.POST.get('services')
        consultation_fee = request.POST.get('consultation_fee')

        doctor.clinic_hospital = clinic_hospital
        doctor.address = address
        doctor.availability = availability
        doctor.services = services

        try:
            doctor.consultation_fee = float(consultation_fee) if consultation_fee else None
        except ValueError:
            messages.error(request, "Invalid consultation fee. Please enter a valid number.")
            return render(request, 'appointments/doctor_profile.html', {"doctor": doctor})

        doctor.save()
        messages.success(request, "Work details updated successfully!")
        return redirect('doctor_profile')  

@login_required
def update_doctor_profile_details(request):
    try:
        doctor = request.user.doctor_profile  
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    if request.method == 'POST':
       
        contact = request.POST.get('contact')
        website = request.POST.get('website')
        languages_spoken = request.POST.get('languages_spoken')

        doctor.contact = contact
        doctor.website = website
        doctor.languages_spoken = languages_spoken
      
        doctor.save()
        messages.success(request, "Contact details updated successfully!")
        return redirect('doctor_profile')  

@login_required
def update_doctor_profile_additional(request):
    try:
        doctor = request.user.doctor_profile  
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    if request.method == 'POST':
        real_name = request.POST.get('realName')
        date_of_birth = request.POST.get('date_of_birth')
        gender = request.POST.get('gender')
        rating = request.POST.get('rating')

        if real_name:
            name_parts = real_name.split(' ', 1)
            doctor.user.first_name = name_parts[0]
            doctor.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
            doctor.user.save()

        doctor.date_of_birth = date_of_birth if date_of_birth else None
        doctor.gender = gender
        try:
            doctor.rating = float(rating) if rating else 0.0
        except ValueError:
            messages.error(request, "Invalid rating value.")
            return render(request, 'appointments/doctor_profile.html', {"doctor": doctor})

        doctor.save()
        messages.success(request, "Additional details updated successfully!")
        return redirect('doctor_profile') 

@login_required
def update_doctor_profile_availability(request):
    try:
        doctor = request.user.doctor_profile  
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    if request.method == 'POST':
        doctor.monday_start = request.POST.get('monday_start')
        doctor.monday_end = request.POST.get('monday_end')
        doctor.tuesday_start = request.POST.get('tuesday_start')
        doctor.tuesday_end = request.POST.get('tuesday_end')
        doctor.wednesday_start = request.POST.get('wednesday_start')
        doctor.wednesday_end = request.POST.get('wednesday_end')
        doctor.thursday_start = request.POST.get('thursday_start')
        doctor.thursday_end = request.POST.get('thursday_end')
        doctor.friday_start = request.POST.get('friday_start')
        doctor.friday_end = request.POST.get('friday_end')


        doctor.save()
        messages.success(request, "Availability details updated successfully!")
        return redirect('doctor_profile')  

@login_required
def generate_and_save_slots(request):
    if request.method == 'POST':
        try:
            doctor = request.user.doctor_profile  
        except Doctor.DoesNotExist:
            messages.error(request, "Doctor profile not found.")
            return redirect('doctor_profile') 
        
        try:
            # Parse JSON body
            data = json.loads(request.body)
            appointment_duration = int(data.get('appointment_duration'))  # Default to 30 minutes
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid data or appointment duration.'}, status=400)

        print(appointment_duration)

        # Availability data
        availability = {
            'Monday': {'start': doctor.monday_start, 'end': doctor.monday_end},
            'Tuesday': {'start': doctor.tuesday_start, 'end': doctor.tuesday_end},
            'Wednesday': {'start': doctor.wednesday_start, 'end': doctor.wednesday_end},
            'Thursday': {'start': doctor.thursday_start, 'end': doctor.thursday_end},
            'Friday': {'start': doctor.friday_start, 'end': doctor.friday_end},
        }

        created_slots = []  # Track created slots for the response

        # Iterate through each day
        for day, times in availability.items():
            start_time = times['start']
            end_time = times['end']

            if not start_time or not end_time:  # Skip days without availability
                continue

            # Parse start and end times
            start_time = datetime.strptime(start_time, '%H:%M').time()
            end_time = datetime.strptime(end_time, '%H:%M').time()

            # Generate slots for the day
            current_time = datetime.combine(datetime.today(), start_time)
            end_datetime = datetime.combine(datetime.today(), end_time)

            while current_time.time() < end_time:
                slot_start = current_time.time()
                slot_end = (current_time + timedelta(minutes=appointment_duration)).time()

                # Ensure slot_end doesn't exceed end_time
                if slot_end > end_time:
                    break

                # Save the slot to the database
                slot, created = Slot.objects.get_or_create(
                    doctor=doctor,
                    day=day,
                    start_time=slot_start,
                    end_time=slot_end,
                    defaults={'reserved': False}
                )
                if created:
                    created_slots.append({
                        'day': day,
                        'start_time': slot_start.strftime('%H:%M'),
                        'end_time': slot_end.strftime('%H:%M')
                    })

                current_time += timedelta(minutes=appointment_duration)

        # Return success response with created slots
        return JsonResponse({'status': 'success', 'created_slots': created_slots})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

def get_slots(request):
    if request.user.is_authenticated:
        doctor = request.user.doctor_profile  # Assuming the user is a doctor
        slots = Slot.objects.filter(doctor=doctor).order_by('day', 'start_time')

        slots_by_day = {}
        for slot in slots:
            if slot.day not in slots_by_day:
                slots_by_day[slot.day] = []
            slots_by_day[slot.day].append({
                'id': slot.id,  # Include slot ID
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
                'first_week_reserved': slot.first_week_reserved,
                'second_week_reserved': slot.second_week_reserved
            })

        return JsonResponse({'status': 'success', 'slots': slots_by_day})

    return JsonResponse({'status': 'error', 'message': 'User not authenticated'}, status=401)

def delete_all_slots(request):
    if request.user.is_authenticated:
        doctor = request.user.doctor_profile
        Slot.objects.filter(doctor=doctor).delete()
        return JsonResponse({'status': 'success', 'message': 'All slots deleted successfully'})

    return JsonResponse({'status': 'error', 'message': 'User not authenticated'}, status=401)

def delete_slot(request, slot_id):
    if request.user.is_authenticated:
        try:
            doctor = request.user.doctor_profile
            slot = Slot.objects.get(id=slot_id, doctor=doctor)

            print(slot)
            slot.delete()
            return JsonResponse({'status': 'success', 'message': 'Slot deleted successfully'})
        except Slot.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Slot not found'}, status=404)
    return JsonResponse({'status': 'error', 'message': 'User not authenticated'}, status=401)

@login_required
def check_slots(request):
    if request.method == 'GET':
        try:
            doctor = request.user.doctor_profile
        except Doctor.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Doctor profile not found.'}, status=404)

        slots_exist = Slot.objects.filter(doctor=doctor).exists()

        return JsonResponse({'status': 'success', 'slots_exist': slots_exist})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)

@login_required
def add_manual_slot(request):
    if request.method == 'POST':
        try:
            doctor = request.user.doctor_profile
        except Doctor.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Doctor profile not found.'}, status=404)

        data = json.loads(request.body)
        day = data.get('day')  # Get the day from the request
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')

        try:
            # Parse start and end times
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time()

            if start_time >= end_time:
                return JsonResponse({'status': 'error', 'message': 'Start time must be before end time.'}, status=400)

            # Check if slot overlaps with existing ones for the same day
            overlapping_slots = Slot.objects.filter(
                doctor=doctor,
                day=day,
                start_time__lt=end_time,
                end_time__gt=start_time
            )

            if overlapping_slots.exists():
                return JsonResponse({'status': 'error', 'message': 'Slot overlaps with an existing one.'}, status=400)

            # Create the new slot
            Slot.objects.create(
                doctor=doctor,
                day=day,  # Use the specified day
                start_time=start_time,
                end_time=end_time,
                reserved=False
            )

            return JsonResponse({'status': 'success', 'message': 'Slot successfully created.'})

        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid time format.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


@login_required
def fetch_slots_for_two_weeks(request, doctor_username):
    try:
        # Retrieve the doctor based on the username
        doctor = get_object_or_404(Doctor, user__username=doctor_username)

        # Today's date
        today = datetime.today().date()

        # Generate the next 14 days with their corresponding day names and week numbers
        next_two_weeks = []
        for i in range(14):
            current_date = today + timedelta(days=i)
            day_name = current_date.strftime('%A')
            week_number = 1 if i < 7 else 2  # First week: days 0-6, Second week: days 7-13
            next_two_weeks.append({
                'date': current_date,
                'day_name': day_name,
                'week': week_number
            })

        # Extract unique day names to minimize database queries
        unique_day_names = {day['day_name'] for day in next_two_weeks}

        # Query slots matching the day names for the doctor
        slots = Slot.objects.filter(
            doctor=doctor,
            day__in=unique_day_names
        ).order_by('day', 'start_time')

        # Organize slots by day name for quick access
        slots_by_day = {}
        for slot in slots:
            slots_by_day.setdefault(slot.day, []).append({
                'id': slot.id,
                'start_time': slot.start_time.strftime('%I:%M %p'),
                'end_time': slot.end_time.strftime('%I:%M %p'),
                'start_time_24h': slot.start_time.strftime('%H:%M'),
                'end_time_24h': slot.end_time.strftime('%H:%M'),
                'first_week_reserved': slot.first_week_reserved,
                'second_week_reserved': slot.second_week_reserved
            })

        # Prepare the slots data structured by date, filtering based on reservation status
        slots_by_date = {}
        for entry in next_two_weeks:
            date = entry['date']
            date_str = date.strftime('%Y-%m-%d')
            day_name = entry['day_name']
            week = entry['week']
            all_slots = slots_by_day.get(day_name, [])

            # Filter slots based on the week and reservation status
            if week == 1:
                available_slots = [
                    {
                        'start_time': slot['start_time'],
                        'end_time': slot['end_time'],
                        'start_time_24h': slot['start_time_24h'],
                        'end_time_24h': slot['end_time_24h']
                    }
                    for slot in all_slots if not slot['first_week_reserved']
                ]
            else:
                available_slots = [
                    {
                        'start_time': slot['start_time'],
                        'end_time': slot['end_time'],
                        'start_time_24h': slot['start_time_24h'],
                        'end_time_24h': slot['end_time_24h']
                    }
                    for slot in all_slots if not slot['second_week_reserved']
                ]

            slots_by_date[date_str] = available_slots

        return JsonResponse({'status': 'success', 'slots': slots_by_date})

    except Exception as e:
        # Log the exception if necessary
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def fetch_slots_for_two_weeks_by_id(request, doctor_id):
    try:
        doctor = get_object_or_404(Doctor, id=doctor_id)  # Get the doctor by id

        # Define the next 14 days with their corresponding dates and day names
        today = datetime.today()
        next_two_weeks = [
            {
                'date': today + timedelta(days=i),
                'day_name': (today + timedelta(days=i)).strftime('%A')
            }
            for i in range(14)
        ]

        # Extract unique day names to minimize database queries
        unique_day_names = {day['day_name'] for day in next_two_weeks}

        # Determine the week (first or second) for each day in the next two weeks
        slots_by_date = {}
        for i, entry in enumerate(next_two_weeks):
            date_obj = entry['date']
            day_name = entry['day_name']
            reserved_field = 'first_week_reserved' if i < 7 else 'second_week_reserved'

            # Query slots for the specific day and exclude reserved slots
            slots = Slot.objects.filter(
                doctor=doctor,
                day=day_name,
                **{reserved_field: False}  # Exclude reserved slots
            ).order_by('start_time')

            # Format slots for JSON response
            formatted_slots = [
                {
                    'start_time': slot.start_time.strftime('%I:%M %p'),
                    'end_time': slot.end_time.strftime('%I:%M %p'),
                    'start_time_24h': slot.start_time.strftime('%H:%M'),
                    'end_time_24h': slot.end_time.strftime('%H:%M'),
                }
                for slot in slots
            ]

            # Add slots to the corresponding date
            date_str = date_obj.strftime('%Y-%m-%d')
            slots_by_date[date_str] = formatted_slots

        return JsonResponse({'status': 'success', 'slots': slots_by_date})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



@login_required
def book_appointment(request):
    if request.method == 'POST':
        try:
            # Get form data
            doctor_id = request.POST.get('doctor_id')
            date = request.POST.get('start_date')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            clinic = request.POST.get('clinic')
            one_time = request.POST.get('one_time') == 'on'  # Checkbox checked
            repeat_every = request.POST.get('repeat_every')
            repeat_unit = request.POST.get('repeat_unit')
            end_date = request.POST.get('end_date')

            # Validate required fields
            if not all([doctor_id, date, start_time, end_time, clinic]):
                return JsonResponse({'error': 'All required fields must be provided.'}, status=400)

            # Convert strings to datetime
            try:
                start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
                end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
            except ValueError:
                return JsonResponse({'error': 'Invalid date or time format.'}, status=400)

            # Validate time logic
            if start_datetime >= end_datetime:
                return JsonResponse({'error': 'Start time must be earlier than end time.'}, status=400)

            # Convert date to day of the week
            try:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return JsonResponse({'error': 'Invalid date format.'}, status=400)

            day_of_week = calendar.day_name[date_obj.weekday()]  # E.g., "Monday"

            # Determine the current date
            today = datetime.today().date()
            selected_date = date_obj.date()
            delta_days = (selected_date - today).days

            if delta_days < 0:
                return JsonResponse({'error': 'Selected date is in the past.'}, status=400)
            elif 0 <= delta_days < 7:
                # Week 1
                reserved_field = 'first_week_reserved'
            elif 7 <= delta_days < 14:
                # Week 2
                reserved_field = 'second_week_reserved'
            else:
                return JsonResponse({'error': 'Selected date is beyond the reservation period (14 days).'}, status=400)

            slot_exists = Slot.objects.filter(
                doctor_id=doctor_id,
                day=day_of_week,
                start_time=start_datetime.time(),
                end_time=end_datetime.time(),
                **{reserved_field: False}  # Dynamically set the reserved field
            ).exists()

            if not slot_exists:
                return JsonResponse({'error': 'The selected slot does not exist.'}, status=400)


            # Handle one-time appointments
            if one_time:
                # Get the doctor
                doctor = get_object_or_404(Doctor, id=doctor_id)

                    # Get the client profile
                try:
                    client = request.user.client_profile
                except AttributeError:
                    return JsonResponse({'error': 'Client profile not found.'}, status=400)

                appointment = Appointment.objects.create(
                    doctor_id=doctor.id,
                    doctor_name=f"Dr. {doctor.user.first_name} {doctor.user.last_name}",
                    doctor_gender=doctor.gender,
                    doctor_contact=doctor.contact,
                    doctor_address=doctor.address,
                    doctor_clinic=doctor.clinic_hospital,

                    start_date=start_datetime.date(),
                    start_time=start_datetime.time(),
                    end_time=end_datetime.time(),
                    duration=(end_datetime - start_datetime).seconds // 60,
                    status=False,
                    one_time_only=True,

                    client_id=client.user.id,
                    client_name=f"{client.user.first_name} {client.user.last_name}",
                    client_gender=client.gender,
                    client_contact=client.contact,
                    client_address = client.address,
                    client_date_of_birth = client.date_of_birth,
                )

                # Generate the email confirmation link
                token = serializer.dumps(appointment.id, salt="appointment-confirmation")
                confirmation_link = f'{settings.RESET_LINK_BASE_URL}/confirm-appointment-by-link/{token}/'

                send_mail(
                    subject='Appointment Confirmation',
                    message=(
                        f"Dear {client.user.first_name} {client.user.last_name},\n\n"
                        f"Your appointment details are as follows:\n"
                        f"Doctor: Dr. {doctor.user.first_name} {doctor.user.last_name}\n"
                        f"Clinic: {doctor.clinic_hospital}\n"
                        f"Address: {doctor.address}\n"
                        f"Date: {start_datetime.date()}\n"
                        f"Time: {start_datetime.time()} - {end_datetime.time()}\n"
                        f"Duration: {(end_datetime - start_datetime).seconds // 60} minutes\n\n"
                        f"To confirm your appointment, please click the following link:\n"
                        f"{confirmation_link}\n\n"
                        f"Thank you,\n"
                        f"Your Clinic Team"
                    ),
                    from_email='mihnea.e@bridge-global.com',
                    recipient_list=['mihnea.encean2@gmail.com'],
                    fail_silently=False,
                )


                messages.success(request, "Appointment booked successfully! An email has been sent to confirm your appointment. Please check your inbox.")

                return redirect('client_appointments')
                #return JsonResponse({'success': 'Appointment booked successfully!'}, status=200)

            if not one_time:
                return JsonResponse({'error': 'Recurring appointments are not yet implemented. One time must be checked'}, status=400)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method.'}, status=405)


def confirm_appointment(request, token):
    try:
        appointment_id = serializer.loads(token, salt="appointment-confirmation", max_age=3600)  # Token valid for 1 hour
        appointment = Appointment.objects.get(id=appointment_id)

        if appointment.status:
            messages.info(request, "This appointment has already been confirmed.")
        else:
            appointment.status = True
            appointment.save()
            messages.success(request, "Your appointment has been successfully confirmed!")
    except (Appointment.DoesNotExist, ValueError):
        messages.error(request, "Invalid or expired confirmation link.")

    return redirect('client_appointments')


@login_required
def upload_clinic_photo(request):
    if request.method == 'POST':
        clinic_photo = request.FILES.get('clinic_photo')
        if clinic_photo:
            doctor = request.user.doctor_profile
            doctor.clinic_picture = clinic_photo
            doctor.save()
            return redirect('doctor_profile')  


def create_account(request):
    return render(request, 'appointments/create_account.html')

def custom_logout(request):
    logout(request)
    return redirect('home')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:

                login(request, user)
                messages.success(request, "You are now logged in.")

                next_url = request.GET.get('next', 'home')  
                return redirect(next_url)
            else:
                messages.error(request, "Your account is deactivated. Please contact support.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'registration/login.html')

def register_doctor(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        name = request.POST.get('realname')
        email = request.POST.get('email')
        password = request.POST.get('password')
        repassword = request.POST.get('repassword')

        if password != repassword:
            messages.error(request, "Passwords do not match.")
            return render(request, 'appointments/register_doctor.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, "This email address already exists.")
            return render(request, 'appointments/register_doctor.html')

        user = User.objects.create_user(
            username=username,  
            email=email,
            password=password, 
            first_name=name.split(' ')[0],  
            last_name=' '.join(name.split(' ')[1:])  
        )

        doctor_group, created = Group.objects.get_or_create(name='Doctor')
        user.groups.add(doctor_group)

        Doctor.objects.create(user=user)

        messages.success(request, "Account created successfully! Please log in.")
        return redirect('login')  

    return render(request, 'appointments/register_doctor.html')

def register_client(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        name = request.POST.get('realname')
        email = request.POST.get('email')
        password = request.POST.get('password')
        repassword = request.POST.get('repassword')

        if password != repassword:
            messages.error(request, "Passwords do not match.")
            return render(request, 'appointments/register_client.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, "This email address already exists.")
            return render(request, 'appointments/register_client.html')

        user = User.objects.create_user(
            username=username,  
            email=email,
            password=password, 
            first_name=name.split(' ')[0],  
            last_name=' '.join(name.split(' ')[1:])  
        )

        client_group, created = Group.objects.get_or_create(name='Client')
        user.groups.add(client_group)

        Client.objects.create(user=user)

        messages.success(request, "Account created successfully! Please log in.")
        return redirect('login')  

    return render(request, 'appointments/register_client.html')


def send_reset_email_client(request):
    
    if request.method == 'POST':
        email = request.POST.get('email')

        print(email)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, 'No user is associated with this email.')
            return redirect('send_reset_email_client')

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_link = f'{settings.RESET_LINK_BASE_URL}/reset-password-by-link/{uid}/{token}/'

        send_mail(
            subject='Password Reset Request',
            message=f'Click this link to reset your password: {reset_link}',
            from_email='mihnea.e@bridge-global.com',  
            recipient_list=[email],
            fail_silently=False,
        )

        messages.success(request, 'Email sent successfully! Please check your inbox.')
        return redirect('client_profile')

        #if hasattr(user, 'client_profile'):
            #return redirect('client_profile')  
        #elif hasattr(user, 'doctor_profile'):
            #return redirect('doctor_profile') 

def send_reset_email_doctor(request):

    if request.method == 'POST':
        email = request.POST.get('email')

        print(email)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, 'No user is associated with this email.')
            return redirect('send_reset_email_doctor')

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_link = f'{settings.RESET_LINK_BASE_URL}/reset-password-by-link/{uid}/{token}/'

        send_mail(
            subject='Password Reset Request',
            message=f'Click this link to reset your password: {reset_link}',
            from_email='mihnea.e@bridge-global.com',  
            recipient_list=[email],
            fail_silently=False,
        )

        messages.success(request, 'Email sent successfully! Please check your inbox.')

        return redirect('doctor_profile')

    return redirect('doctor_profile')

        #if hasattr(user, 'client_profile'):
            #return redirect('client_profile')  
        #elif hasattr(user, 'doctor_profile'):
            #return redirect('doctor_profile') 

def send_contact_site_email(request):
    if request.method == 'POST':
        first_name = request.POST.get('firstName')
        last_name = request.POST.get('lastName')
        mobile_phone = request.POST.get('mobile')
        email = request.POST.get('email')
        message = request.POST.get('message')

        subject = f"Contact Form Submission from {first_name} {last_name}"
        body = (
            f"You have received a new contact form submission:\n\n"
            f"Name: {first_name} {last_name}\n"
            f"Mobile Phone: {mobile_phone}\n"
            f"Email: {email}\n\n"
            f"Message:\n{message}\n"
        )
        recipient_list = ['mihnea.encean2@gmail.com']  
        
        try:
            send_mail(
                subject,
                body,
                'mihnea.e@bridge-global.com',  
                recipient_list,
                fail_silently=False,  
            )

            return JsonResponse({'status': 'success', 'message': 'Email sent successfully!'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Failed to send email: {str(e)}"})
        

def reset_password_view(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                return render(request, 'appointments/reset_password.html', {'validlink': True})

            user.set_password(new_password)
            user.save()
            messages.success(request, "Password reset successfully! Please log in with your new password.")
            return redirect('login')

        return render(request, 'appointments/reset_password.html', {'validlink': True})
    else:
        messages.error(request, "The reset password link is invalid or expired.")
        return render(request, 'appointments/reset_password.html', {'validlink': False})

def about(request):
    return render(request, 'appointments/about.html')

def doctor_appointments(request):
    try:
        doctor = request.user.doctor_profile
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")

    appointments = Appointment.objects.filter(doctor_id=doctor.id).order_by('-start_date', '-start_time')

    current_time = now()

    total_appointments = appointments.count()
    finished_appointments = appointments.filter(end_time__lte=current_time.time(), start_date__lte=current_time.date()).count()
    active_appointments = appointments.filter(end_time__gt=current_time.time(), start_date__gte=current_time.date()).count()

    current_time_for_compare = timezone.now()

    for appointment in appointments:
        appointment.is_active = (
            appointment.start_date >= current_time_for_compare.date() and 
            appointment.end_time > current_time_for_compare.time()
        )   

    active_appointments_filtered = appointments.filter(
        end_time__gt=current_time.time(),
        start_date__gte=current_time.date()
    )

    finished_appointments_filtered = appointments.filter(
        end_time__lte=current_time.time(),
    )

    context  = {
        'appointments': appointments,
        'active_appointments_filtered': active_appointments_filtered,
        'finished_appointments_filtered': finished_appointments_filtered,
        'total_appointments': total_appointments,
        'finished_appointments': finished_appointments,
        'active_appointments': active_appointments,
        'current_date': current_time.strftime('%d %b %Y'),
    }

    return render(request, 'appointments/doctor_appointments.html', context)

def client_appointments(request):
    try:
        client = request.user.client_profile  
    except Client.DoesNotExist:
        messages.error(request, "Client profile not found.")

    appointments = Appointment.objects.filter(client_id=request.user.id).order_by('-start_date', '-start_time')

    current_time = now()

    total_appointments = appointments.count()
    finished_appointments = appointments.filter(end_time__lte=current_time.time(), start_date__lte=current_time.date()).count()
    active_appointments = appointments.filter(end_time__gt=current_time.time(), start_date__gte=current_time.date()).count()

    current_time_for_compare = timezone.now()

    for appointment in appointments:
        appointment.is_active = (
            appointment.start_date >= current_time_for_compare.date() and 
            appointment.end_time > current_time_for_compare.time()
        )   

    active_appointments_filtered = appointments.filter(
        end_time__gt=current_time.time(),
        start_date__gte=current_time.date()
    )

    finished_appointments_filtered = appointments.filter(
        end_time__lte=current_time.time(),
        start_date__lte=current_time.date()
    )

    context  = {
        'appointments': appointments,
        'active_appointments_filtered': active_appointments_filtered,
        'finished_appointments_filtered': finished_appointments_filtered,
        'total_appointments': total_appointments,
        'finished_appointments': finished_appointments,
        'active_appointments': active_appointments,
        'current_date': current_time.strftime('%d %b %Y'),
    }

    return render(request, 'appointments/client_appointments.html', context)

def client_profile(request):
    try:
        client = request.user.client_profile  
    except Client.DoesNotExist:
        messages.error(request, "Client profile not found.")
    
    return render(request, 'appointments/client_profile.html', {"client" : client})

def doctor_profile(request):
    try:
        doctor = request.user.doctor_profile
    except Doctor.DoesNotExist:
        messages.error(request, "Doctor profile not found.")
        return redirect('doctor_profile')

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    hours = list(range(24))
    minutes = list(range(0, 60, 10))

    # Create a list of availability items
    availability_list = []
    for day in days:
        day_lower = day.lower()
        availability_list.append({
            'day': day,                   # e.g. "Monday"
            'day_lower': day_lower,       # e.g. "monday"
            'start': getattr(doctor, f"{day_lower}_start", None),
            'end': getattr(doctor, f"{day_lower}_end", None),
        })

    duration_list = [i for i in range(10, 121, 10)] 

    context = {
        "doctor": doctor,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "availability_list": availability_list,
        'duration_list': duration_list,
    }

    return render(request, 'appointments/doctor_profile.html', context)


def contact(request):

    


    return render(request, 'appointments/contact.html')

def subscription(request):
    return render(request, 'appointments/subscription.html')

def forgot_password(request):
    return render(request, 'appointments/forgot_password.html')

def search_results(request):
    query = request.GET.get('q', '')

    return render(request, 'appointments/search_results.html', {'query': query})

def view_doctor_profile_by_cli(request, username):
    doctor = get_object_or_404(Doctor, user__username=username)

    return render(request, 'appointments/view_doctor_profile_by_cli.html', {'doctor': doctor})

