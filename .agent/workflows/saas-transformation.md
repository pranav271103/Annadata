---
description: Transform OCR Portal into Multi-Tenant SaaS with Subscription Management
---

# SaaS Transformation Implementation Plan

## 🎯 Objective
Convert the OCR Portal into a full-fledged SaaS platform where:
- **Clients** can purchase subscriptions
- **Clients** can manage multiple **Organizations**
- **Organizations** can have multiple **Users**
- **Subscription tiers**: Silver (₹5,000/2,500 invoices), Gold (₹10,000/7,000 invoices), Platinum (₹25,000/20,000 invoices)
- **Razorpay** integration for payments
- **Self-service registration** and login

---

## 📊 Current Architecture Analysis

### ✅ Existing Components
1. **Client Model** (`ocr_app/models.py:719`)
   - One-to-one with User
   - Many-to-many with Organizations
   - Basic profile fields

2. **Organization Model** (`ocr_app/models.py:17`)
   - Core tenant model
   - Has settings, users, batches, documents

3. **Billing & Payment Models** (`ocr_app/models.py:278-333`)
   - Billing per organization per month
   - Payment tracking
   - Advance payments

4. **Razorpay Integration** (`ocr_app/views.py:848-954`)
   - Order creation
   - Webhook handling
   - Payment verification

5. **Client Dashboard** (`ocr_app/views.py:1908`)
   - Organization summary view
   - Usage statistics (invoices, pages)

6. **Usage Tracking** (`ocr_app/models.py:260`)
   - Monthly usage rollups
   - Files and pages processed

### ❌ Missing Components
1. **Subscription Plans** - No model for plan tiers
2. **Client Subscriptions** - No link between Client and Plan
3. **Usage Limits** - No enforcement of invoice limits
4. **Self-Registration** - No public signup flow
5. **Subscription Dashboard** - No dedicated subscription management UI
6. **Plan Selection UI** - No checkout flow for plans

---

## 🏗️ Implementation Tasks

### **Phase 1: Database Models** (Priority: P0)

#### Task 1.1: Create Subscription Plan Model
**File**: `ocr_app/models.py`
**Action**: Add new model after `Client` model

```python
class SubscriptionPlan(models.Model):
    """
    Defines available subscription tiers
    """
    PLAN_CHOICES = [
        ('SILVER', 'Silver'),
        ('GOLD', 'Gold'),
        ('PLATINUM', 'Platinum'),
    ]
    
    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in INR")
    invoice_limit = models.PositiveIntegerField(help_text="Monthly invoice processing limit")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    features = models.JSONField(default=list, help_text="List of features")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "subscription_plans"
    
    def __str__(self):
        return f"{self.display_name} - ₹{self.price}/month"
```

#### Task 1.2: Create Client Subscription Model
**File**: `ocr_app/models.py`
**Action**: Add new model after `SubscriptionPlan`

```python
class ClientSubscription(models.Model):
    """
    Links Client to a Subscription Plan with billing cycle tracking
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
        ('PENDING', 'Pending Payment'),
    ]
    
    client = models.ForeignKey(
        'Client',
        on_delete=models.CASCADE,
        related_name='subscriptions',
        db_index=True
    )
    plan = models.ForeignKey(
        'SubscriptionPlan',
        on_delete=models.PROTECT,
        related_name='subscriptions'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Billing cycle
    start_date = models.DateField()
    end_date = models.DateField()
    auto_renew = models.BooleanField(default=True)
    
    # Usage tracking
    invoices_processed = models.PositiveIntegerField(default=0, help_text="Invoices processed in current cycle")
    
    # Payment tracking
    razorpay_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    last_payment_date = models.DateTimeField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "client_subscriptions"
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['end_date', 'status']),
        ]
    
    def __str__(self):
        return f"{self.client} - {self.plan.display_name} ({self.status})"
    
    @property
    def is_active(self):
        return self.status == 'ACTIVE' and self.end_date >= timezone.now().date()
    
    @property
    def usage_percentage(self):
        if self.plan.invoice_limit == 0:
            return 0
        return (self.invoices_processed / self.plan.invoice_limit) * 100
    
    @property
    def invoices_remaining(self):
        return max(0, self.plan.invoice_limit - self.invoices_processed)
```

#### Task 1.3: Create Subscription Payment Model
**File**: `ocr_app/models.py`
**Action**: Add new model after `ClientSubscription`

```python
class SubscriptionPayment(models.Model):
    """
    Tracks all subscription-related payments
    """
    subscription = models.ForeignKey(
        'ClientSubscription',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    
    # Razorpay details
    razorpay_payment_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_signature = models.CharField(max_length=255)
    
    status = models.CharField(max_length=20, default='PENDING')
    payment_method = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "subscription_payments"
        indexes = [
            models.Index(fields=['subscription', 'created_at']),
        ]
```

#### Task 1.4: Update Client Model
**File**: `ocr_app/models.py`
**Action**: Add helper method to Client model (line 719)

```python
# Add to Client model
def get_active_subscription(self):
    """Returns the currently active subscription, if any"""
    return self.subscriptions.filter(
        status='ACTIVE',
        end_date__gte=timezone.now().date()
    ).first()

def can_process_invoice(self):
    """Check if client has quota to process more invoices"""
    sub = self.get_active_subscription()
    if not sub:
        return False, "No active subscription"
    if sub.invoices_processed >= sub.plan.invoice_limit:
        return False, f"Monthly limit of {sub.plan.invoice_limit} invoices reached"
    return True, "OK"
```

---

### **Phase 2: Database Migration**

#### Task 2.1: Create and Run Migrations
```bash
# Create migrations
python manage.py makemigrations ocr_app

# Review migration file
# Apply migrations
python manage.py migrate
```

#### Task 2.2: Seed Subscription Plans
**File**: Create `ocr_app/management/commands/seed_plans.py`

```python
from django.core.management.base import BaseCommand
from ocr_app.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Seed subscription plans'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'SILVER',
                'display_name': 'Silver Plan',
                'price': 5000.00,
                'invoice_limit': 2500,
                'description': 'Perfect for small businesses',
                'features': [
                    '2,500 invoices/month',
                    'OCR Processing',
                    'Basic Reports',
                    'Email Support'
                ]
            },
            {
                'name': 'GOLD',
                'display_name': 'Gold Plan',
                'price': 10000.00,
                'invoice_limit': 7000,
                'description': 'Ideal for growing companies',
                'features': [
                    '7,000 invoices/month',
                    'OCR Processing',
                    'Advanced Reports',
                    'Priority Support',
                    'API Access'
                ]
            },
            {
                'name': 'PLATINUM',
                'display_name': 'Platinum Plan',
                'price': 25000.00,
                'invoice_limit': 20000,
                'description': 'Enterprise-grade solution',
                'features': [
                    '20,000 invoices/month',
                    'OCR Processing',
                    'Custom Reports',
                    '24/7 Support',
                    'API Access',
                    'Dedicated Account Manager'
                ]
            }
        ]
        
        for plan_data in plans:
            plan, created = SubscriptionPlan.objects.update_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(
                self.style.SUCCESS(f'{status} plan: {plan.display_name}')
            )
```

**Run**: `python manage.py seed_plans`

---

### **Phase 3: Views & Business Logic**

#### Task 3.1: Subscription Management Views
**File**: `ocr_app/views_subscription.py` (new file)

```python
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import razorpay
import hmac
import hashlib

from .models import (
    Client, SubscriptionPlan, ClientSubscription, 
    SubscriptionPayment
)
from .utils import is_client

@login_required
def subscription_plans(request):
    """Display available subscription plans"""
    if not is_client(request.user):
        return redirect('dashboard')
    
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    client = request.user.client_profile
    active_sub = client.get_active_subscription()
    
    return render(request, 'subscription/plans.html', {
        'plans': plans,
        'active_subscription': active_sub
    })

@login_required
def subscribe_to_plan(request, plan_id):
    """Initiate subscription to a plan"""
    if not is_client(request.user):
        return JsonResponse({'error': 'Not authorized'}, status=403)
    
    plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)
    client = request.user.client_profile
    
    # Check if already has active subscription
    active_sub = client.get_active_subscription()
    if active_sub:
        return JsonResponse({
            'error': f'You already have an active {active_sub.plan.display_name} subscription'
        }, status=400)
    
    # Create subscription record
    start_date = timezone.now().date()
    end_date = start_date + timedelta(days=30)  # Monthly subscription
    
    subscription = ClientSubscription.objects.create(
        client=client,
        plan=plan,
        status='PENDING',
        start_date=start_date,
        end_date=end_date,
        auto_renew=True
    )
    
    # Create Razorpay order
    razorpay_client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    
    amount_paise = int(plan.price * 100)
    
    order_data = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': f'sub_{subscription.id}',
        'notes': {
            'subscription_id': subscription.id,
            'client_id': client.id,
            'plan': plan.name
        }
    }
    
    razorpay_order = razorpay_client.order.create(data=order_data)
    
    subscription.razorpay_order_id = razorpay_order['id']
    subscription.save()
    
    return JsonResponse({
        'order_id': razorpay_order['id'],
        'amount': amount_paise,
        'currency': 'INR',
        'key_id': settings.RAZORPAY_KEY_ID,
        'subscription_id': subscription.id,
        'plan_name': plan.display_name
    })

@csrf_exempt
def subscription_webhook(request):
    """Handle Razorpay webhook for subscription payments"""
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    webhook_signature = request.headers.get('X-Razorpay-Signature', '')
    webhook_body = request.body
    
    # Verify signature
    try:
        razorpay.utility.verify_webhook_signature(
            webhook_body.decode('utf-8'),
            webhook_signature,
            webhook_secret
        )
    except:
        return JsonResponse({'status': 'invalid signature'}, status=400)
    
    payload = json.loads(webhook_body)
    event = payload.get('event')
    
    if event == 'payment.captured':
        payment_entity = payload['payload']['payment']['entity']
        order_id = payment_entity.get('order_id')
        payment_id = payment_entity.get('id')
        
        try:
            subscription = ClientSubscription.objects.get(razorpay_order_id=order_id)
            
            # Create payment record
            SubscriptionPayment.objects.create(
                subscription=subscription,
                amount=Decimal(payment_entity['amount']) / 100,
                currency=payment_entity['currency'],
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id,
                razorpay_signature=webhook_signature,
                status='CAPTURED',
                payment_method=payment_entity.get('method', '')
            )
            
            # Activate subscription
            subscription.status = 'ACTIVE'
            subscription.last_payment_date = timezone.now()
            subscription.save()
            
        except ClientSubscription.DoesNotExist:
            pass
    
    return JsonResponse({'status': 'ok'})

@login_required
def client_subscription_dashboard(request):
    """Client's subscription management dashboard"""
    if not is_client(request.user):
        return redirect('dashboard')
    
    client = request.user.client_profile
    active_sub = client.get_active_subscription()
    
    # Get usage statistics across all organizations
    from .models import Document, ExtractedInvoice
    from django.db.models import Count, Sum
    from datetime import datetime
    
    # Current month usage
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    orgs = client.organizations.all()
    
    monthly_stats = Document.objects.filter(
        organization__in=orgs,
        processed_at__gte=month_start
    ).aggregate(
        total_invoices=Count('invoice_extraction'),
        total_pages=Count('pages')
    )
    
    # Payment history
    payment_history = []
    if active_sub:
        payment_history = active_sub.payments.order_by('-created_at')[:10]
    
    context = {
        'client': client,
        'active_subscription': active_sub,
        'organizations': orgs,
        'monthly_stats': monthly_stats,
        'payment_history': payment_history,
    }
    
    return render(request, 'subscription/dashboard.html', context)
```

#### Task 3.2: Update Upload View with Usage Enforcement
**File**: `ocr_app/views.py`
**Action**: Modify `upload_files` function (line 577)

Add at the beginning of the function:
```python
# Check if user is a client and enforce subscription limits
if is_client(request.user):
    client = request.user.client_profile
    can_process, message = client.can_process_invoice()
    if not can_process:
        messages.error(request, f"Upload blocked: {message}")
        return redirect('subscription_dashboard')
```

#### Task 3.3: Update Document Processing to Track Usage
**File**: `ocr_app/views.py` or processing logic
**Action**: After successful invoice extraction, increment counter

```python
# After invoice is successfully extracted
if is_client(request.user):
    client = request.user.client_profile
    active_sub = client.get_active_subscription()
    if active_sub:
        active_sub.invoices_processed += 1
        active_sub.save()
```

---

### **Phase 4: Templates & UI**

#### Task 4.1: Subscription Plans Page
**File**: `templates/subscription/plans.html` (new)

```html
{% extends "base.html" %}
{% block title %}Subscription Plans · Akounter{% endblock %}

{% block content %}
<div class="card" style="margin-top:0;">
  <h1 style="font-size:28px;margin-bottom:8px;">Choose Your Plan</h1>
  <p style="color:#a7b0c6;margin-bottom:24px;">Select the perfect plan for your business needs</p>

  {% if active_subscription %}
  <div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:12px;padding:16px;margin-bottom:24px;">
    <strong>Current Plan:</strong> {{ active_subscription.plan.display_name }} 
    <span style="color:#a7b0c6;">• Valid until {{ active_subscription.end_date|date:"M d, Y" }}</span>
    <br>
    <strong>Usage:</strong> {{ active_subscription.invoices_processed }} / {{ active_subscription.plan.invoice_limit }} invoices 
    ({{ active_subscription.usage_percentage|floatformat:1 }}%)
  </div>
  {% endif %}

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;">
    {% for plan in plans %}
    <div class="plan-card" style="background:rgba(255,255,255,0.04);border:1px solid var(--line);border-radius:16px;padding:24px;">
      <h3 style="font-size:22px;margin:0 0 8px;">{{ plan.display_name }}</h3>
      <div style="font-size:32px;font-weight:700;margin:12px 0;">
        ₹{{ plan.price|floatformat:0 }}
        <span style="font-size:16px;color:#a7b0c6;font-weight:400;">/month</span>
      </div>
      <p style="color:#a7b0c6;margin:12px 0;">{{ plan.description }}</p>
      
      <ul style="list-style:none;padding:0;margin:20px 0;">
        {% for feature in plan.features %}
        <li style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
          <svg style="width:16px;height:16px;color:#22c55e;display:inline-block;margin-right:8px;" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
          </svg>
          {{ feature }}
        </li>
        {% endfor %}
      </ul>

      {% if active_subscription and active_subscription.plan.id == plan.id %}
        <button class="btn" disabled style="width:100%;opacity:0.6;">Current Plan</button>
      {% else %}
        <button class="btn subscribe-btn" data-plan-id="{{ plan.id }}" style="width:100%;background:linear-gradient(180deg,#818cf8,#60a5fa);">
          Subscribe Now
        </button>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</div>

<script src="https://checkout.razorpay.com/v1/checkout.js"></script>
<script>
document.querySelectorAll('.subscribe-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const planId = btn.dataset.planId;
    btn.disabled = true;
    btn.textContent = 'Processing...';
    
    try {
      const response = await fetch(`/subscription/subscribe/${planId}/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': '{{ csrf_token }}',
          'Content-Type': 'application/json'
        }
      });
      
      const data = await response.json();
      
      if (data.error) {
        alert(data.error);
        btn.disabled = false;
        btn.textContent = 'Subscribe Now';
        return;
      }
      
      // Launch Razorpay
      const options = {
        key: data.key_id,
        amount: data.amount,
        currency: data.currency,
        name: 'Akounter OCR',
        description: data.plan_name + ' Subscription',
        order_id: data.order_id,
        handler: function(response) {
          window.location.href = '/subscription/dashboard/';
        },
        prefill: {
          email: '{{ request.user.email }}',
          contact: ''
        }
      };
      
      const rzp = new Razorpay(options);
      rzp.open();
      
    } catch (error) {
      alert('Failed to initiate payment: ' + error.message);
      btn.disabled = false;
      btn.textContent = 'Subscribe Now';
    }
  });
});
</script>
{% endblock %}
```

#### Task 4.2: Subscription Dashboard
**File**: `templates/subscription/dashboard.html` (new)

```html
{% extends "base.html" %}
{% block title %}My Subscription · Akounter{% endblock %}

{% block content %}
<div class="card" style="margin-top:0;">
  <h1 style="font-size:28px;margin-bottom:24px;">Subscription Dashboard</h1>

  <!-- Active Subscription Card -->
  {% if active_subscription %}
  <div style="background:linear-gradient(135deg,rgba(129,140,248,0.1),rgba(96,165,250,0.1));border:1px solid rgba(129,140,248,0.3);border-radius:16px;padding:24px;margin-bottom:24px;">
    <div style="display:flex;justify-content:space-between;align-items:start;">
      <div>
        <h2 style="font-size:24px;margin:0 0 8px;">{{ active_subscription.plan.display_name }}</h2>
        <p style="color:#a7b0c6;margin:0;">₹{{ active_subscription.plan.price|floatformat:0 }}/month</p>
      </div>
      <span class="pill" style="background:rgba(34,197,94,0.2);border-color:rgba(34,197,94,0.4);">{{ active_subscription.status }}</span>
    </div>
    
    <div style="margin-top:20px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.1);">
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
        <div>
          <div style="color:#a7b0c6;font-size:14px;">Valid Until</div>
          <div style="font-size:18px;font-weight:600;margin-top:4px;">{{ active_subscription.end_date|date:"M d, Y" }}</div>
        </div>
        <div>
          <div style="color:#a7b0c6;font-size:14px;">Invoices Used</div>
          <div style="font-size:18px;font-weight:600;margin-top:4px;">
            {{ active_subscription.invoices_processed }} / {{ active_subscription.plan.invoice_limit }}
          </div>
        </div>
        <div>
          <div style="color:#a7b0c6;font-size:14px;">Remaining</div>
          <div style="font-size:18px;font-weight:600;margin-top:4px;color:#22c55e;">
            {{ active_subscription.invoices_remaining }}
          </div>
        </div>
      </div>
      
      <!-- Usage Progress Bar -->
      <div style="margin-top:16px;">
        <div style="background:rgba(255,255,255,0.1);border-radius:999px;height:8px;overflow:hidden;">
          <div style="background:linear-gradient(90deg,#818cf8,#60a5fa);height:100%;width:{{ active_subscription.usage_percentage }}%;transition:width 0.3s;"></div>
        </div>
        <div style="color:#a7b0c6;font-size:12px;margin-top:4px;">{{ active_subscription.usage_percentage|floatformat:1 }}% used</div>
      </div>
    </div>
  </div>
  {% else %}
  <div style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.3);border-radius:12px;padding:20px;margin-bottom:24px;text-align:center;">
    <p style="margin:0;font-size:16px;">You don't have an active subscription.</p>
    <a href="{% url 'subscription_plans' %}" class="btn" style="margin-top:12px;display:inline-block;">View Plans</a>
  </div>
  {% endif %}

  <!-- Current Month Usage -->
  <div style="margin-bottom:24px;">
    <h3 style="font-size:20px;margin-bottom:16px;">This Month's Activity</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
      <div class="stat-card" style="background:rgba(255,255,255,0.04);border:1px solid var(--line);border-radius:12px;padding:20px;">
        <div style="color:#a7b0c6;font-size:14px;">Invoices Processed</div>
        <div style="font-size:32px;font-weight:700;margin-top:8px;">{{ monthly_stats.total_invoices|default:0 }}</div>
      </div>
      <div class="stat-card" style="background:rgba(255,255,255,0.04);border:1px solid var(--line);border-radius:12px;padding:20px;">
        <div style="color:#a7b0c6;font-size:14px;">Pages Scanned</div>
        <div style="font-size:32px;font-weight:700;margin-top:8px;">{{ monthly_stats.total_pages|default:0 }}</div>
      </div>
      <div class="stat-card" style="background:rgba(255,255,255,0.04);border:1px solid var(--line);border-radius:12px;padding:20px;">
        <div style="color:#a7b0c6;font-size:14px;">Organizations</div>
        <div style="font-size:32px;font-weight:700;margin-top:8px;">{{ organizations.count }}</div>
      </div>
    </div>
  </div>

  <!-- Organizations List -->
  <div style="margin-bottom:24px;">
    <h3 style="font-size:20px;margin-bottom:16px;">Your Organizations</h3>
    <table class="table">
      <thead>
        <tr>
          <th>Organization Name</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for org in organizations %}
        <tr class="card" style="display:table-row;">
          <td>{{ org.name }}</td>
          <td><span class="pill">{% if org.is_active %}Active{% else %}Inactive{% endif %}</span></td>
          <td><a href="{% url 'dashboard' %}" class="auth-link">View →</a></td>
        </tr>
        {% empty %}
        <tr><td colspan="3">No organizations yet.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Payment History -->
  {% if payment_history %}
  <div>
    <h3 style="font-size:20px;margin-bottom:16px;">Payment History</h3>
    <table class="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Amount</th>
          <th>Payment ID</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for payment in payment_history %}
        <tr class="card" style="display:table-row;">
          <td>{{ payment.created_at|date:"M d, Y H:i" }}</td>
          <td>₹{{ payment.amount|floatformat:2 }}</td>
          <td><code style="font-size:12px;">{{ payment.razorpay_payment_id }}</code></td>
          <td><span class="pill">{{ payment.status }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
</div>
{% endblock %}
```

#### Task 4.3: Update Navigation for Clients
**File**: `templates/base.html`
**Action**: Add subscription link in navigation for clients

```html
{% if request.user.is_authenticated and request.user.client_profile %}
<a href="{% url 'subscription_dashboard' %}" class="nav-link">My Subscription</a>
{% endif %}
```

---

### **Phase 5: URL Configuration**

#### Task 5.1: Add Subscription URLs
**File**: `ocr_app/urls.py`
**Action**: Add new URL patterns

```python
from .views_subscription import (
    subscription_plans,
    subscribe_to_plan,
    subscription_webhook,
    client_subscription_dashboard
)

# Add to urlpatterns
path('subscription/plans/', subscription_plans, name='subscription_plans'),
path('subscription/subscribe/<int:plan_id>/', subscribe_to_plan, name='subscribe_to_plan'),
path('subscription/webhook/', subscription_webhook, name='subscription_webhook'),
path('subscription/dashboard/', client_subscription_dashboard, name='subscription_dashboard'),
```

---

### **Phase 6: Self-Service Registration**

#### Task 6.1: Public Registration View
**File**: `ocr_app/views_auth.py` (new)

```python
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Client

def register_client(request):
    """Public registration for new clients"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        company_name = request.POST.get('company_name')
        contact_phone = request.POST.get('contact_phone')
        
        # Validation
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return render(request, 'auth/register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
            return render(request, 'auth/register.html')
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=company_name
        )
        
        # Create client profile
        Client.objects.create(
            user=user,
            company_name=company_name,
            contact_email=email,
            contact_phone=contact_phone
        )
        
        # Auto-login
        login(request, user)
        
        messages.success(request, 'Account created successfully! Please choose a subscription plan.')
        return redirect('subscription_plans')
    
    return render(request, 'auth/register.html')
```

#### Task 6.2: Registration Template
**File**: `templates/auth/register.html` (new)

```html
{% extends "base.html" %}
{% block title %}Register · Akounter{% endblock %}

{% block content %}
<div style="max-width:500px;margin:60px auto;padding:0 20px;">
  <div class="card">
    <h1 style="font-size:28px;margin-bottom:8px;text-align:center;">Create Your Account</h1>
    <p style="color:#a7b0c6;text-align:center;margin-bottom:32px;">Start processing invoices with AI</p>

    {% if messages %}
    {% for message in messages %}
    <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:12px;margin-bottom:16px;">
      {{ message }}
    </div>
    {% endfor %}
    {% endif %}

    <form method="post">
      {% csrf_token %}
      
      <div style="margin-bottom:16px;">
        <label style="display:block;margin-bottom:6px;font-weight:500;">Username</label>
        <input type="text" name="username" required 
               style="width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,0.05);">
      </div>

      <div style="margin-bottom:16px;">
        <label style="display:block;margin-bottom:6px;font-weight:500;">Email</label>
        <input type="email" name="email" required 
               style="width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,0.05);">
      </div>

      <div style="margin-bottom:16px;">
        <label style="display:block;margin-bottom:6px;font-weight:500;">Password</label>
        <input type="password" name="password" required 
               style="width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,0.05);">
      </div>

      <div style="margin-bottom:16px;">
        <label style="display:block;margin-bottom:6px;font-weight:500;">Company Name</label>
        <input type="text" name="company_name" required 
               style="width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,0.05);">
      </div>

      <div style="margin-bottom:24px;">
        <label style="display:block;margin-bottom:6px;font-weight:500;">Contact Phone</label>
        <input type="tel" name="contact_phone" 
               style="width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:rgba(255,255,255,0.05);">
      </div>

      <button type="submit" class="btn" style="width:100%;background:linear-gradient(180deg,#818cf8,#60a5fa);padding:14px;">
        Create Account
      </button>
    </form>

    <p style="text-align:center;margin-top:20px;color:#a7b0c6;">
      Already have an account? <a href="{% url 'login' %}" class="auth-link">Sign in</a>
    </p>
  </div>
</div>
{% endblock %}
```

#### Task 6.3: Add Registration URL
**File**: `ocr_app/urls.py`

```python
from .views_auth import register_client

# Add to urlpatterns
path('register/', register_client, name='register'),
```

---

### **Phase 7: Admin Panel Configuration**

#### Task 7.1: Register New Models in Admin
**File**: `ocr_app/admin.py`

```python
from .models import SubscriptionPlan, ClientSubscription, SubscriptionPayment

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'price', 'invoice_limit', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'display_name']

@admin.register(ClientSubscription)
class ClientSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['client', 'plan', 'status', 'start_date', 'end_date', 'invoices_processed']
    list_filter = ['status', 'plan']
    search_fields = ['client__user__username', 'client__company_name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ['subscription', 'amount', 'status', 'created_at', 'razorpay_payment_id']
    list_filter = ['status']
    search_fields = ['razorpay_payment_id', 'razorpay_order_id']
    readonly_fields = ['created_at']
```

---

### **Phase 8: Testing**

#### Task 8.1: Browser Testing Checklist
1. **Registration Flow**
   - [ ] Navigate to `/register/`
   - [ ] Fill form and submit
   - [ ] Verify redirect to subscription plans
   - [ ] Verify Client profile created

2. **Subscription Purchase**
   - [ ] Select a plan
   - [ ] Verify Razorpay checkout opens
   - [ ] Complete test payment
   - [ ] Verify subscription activated
   - [ ] Check subscription dashboard

3. **Usage Tracking**
   - [ ] Upload documents as client
   - [ ] Verify invoice counter increments
   - [ ] Test limit enforcement
   - [ ] Verify error when limit reached

4. **Client Dashboard**
   - [ ] View subscription details
   - [ ] Check usage statistics
   - [ ] View payment history
   - [ ] List organizations

5. **Organization Summary**
   - [ ] Access as client
   - [ ] Verify multi-org data display
   - [ ] Filter by month

---

### **Phase 9: Deployment Preparation**

#### Task 9.1: Environment Variables
**File**: `.env` or server config

```bash
# Razorpay Configuration
RAZORPAY_KEY_ID=your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
```

#### Task 9.2: Webhook Configuration
1. Login to Razorpay Dashboard
2. Go to Settings → Webhooks
3. Add webhook URL: `https://yourdomain.com/subscription/webhook/`
4. Select events: `payment.captured`, `payment.failed`
5. Copy webhook secret to environment

---

## 🎯 Verification Criteria

### Success Metrics
- [ ] New users can self-register
- [ ] Clients can view and purchase subscription plans
- [ ] Razorpay payment integration works end-to-end
- [ ] Subscription status updates automatically after payment
- [ ] Invoice processing increments usage counter
- [ ] System blocks uploads when limit is reached
- [ ] Client dashboard shows accurate usage statistics
- [ ] Multi-organization support works for clients
- [ ] Payment history is tracked and displayed

### Performance Checks
- [ ] Dashboard loads in < 2 seconds
- [ ] Razorpay checkout opens smoothly
- [ ] Webhook processes payments within 5 seconds
- [ ] No N+1 queries in subscription dashboard

---

## 📝 Notes

1. **Razorpay Test Mode**: Use test keys during development
2. **Subscription Renewal**: Implement cron job for auto-renewal (future enhancement)
3. **Prorated Billing**: Not implemented in v1 (future enhancement)
4. **Plan Upgrades**: Not implemented in v1 (future enhancement)
5. **Invoice Limits**: Reset monthly via cron job (implement separately)

---

## 🚀 Execution Order

1. Phase 1: Database Models
2. Phase 2: Migrations & Seeding
3. Phase 3: Views & Logic
4. Phase 4: Templates
5. Phase 5: URLs
6. Phase 6: Registration
7. Phase 7: Admin
8. Phase 8: Testing
9. Phase 9: Deployment

**Estimated Time**: 6-8 hours for full implementation
