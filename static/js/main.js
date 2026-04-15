/**
 * ISKCON Book Store — Main JavaScript
 * Handles: Cart AJAX, Qty picker, Toast notifications,
 *          Razorpay, Search, Coupon feedback
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ──────────────────────────────────
     Toast Notifications
  ────────────────────────────────── */
  const toastContainer = document.createElement('div');
  toastContainer.id = 'toast-container';
  document.body.appendChild(toastContainer);

  function showToast(message, type = 'success', duration = 3000) {
    const icons = { success: '✅', danger: '❌', warning: '⚠️', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = 'iskcon-toast';
    toast.innerHTML = `<span>${icons[type] || '🙏'}</span><span>${message}</span>`;
    toast.style.borderLeftColor = type === 'danger' ? '#dc3545'
                                : type === 'warning' ? '#ffc107'
                                : type === 'info'    ? '#17a2b8'
                                : 'var(--saffron)';
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = 'slideInRight 0.3s ease reverse';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // Auto-dismiss Bootstrap alerts
  document.querySelectorAll('.alert-dismissible').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 4000);
  });

  /* ──────────────────────────────────
     Quantity Picker
  ────────────────────────────────── */
  document.querySelectorAll('.qty-picker').forEach(picker => {
    const input = picker.querySelector('input[type="number"]');
    const minusBtn = picker.querySelector('[data-action="minus"]');
    const plusBtn  = picker.querySelector('[data-action="plus"]');
    const max = parseInt(input.max) || 99;

    minusBtn?.addEventListener('click', () => {
      const val = parseInt(input.value) || 1;
      input.value = Math.max(1, val - 1);
      input.dispatchEvent(new Event('change'));
    });

    plusBtn?.addEventListener('click', () => {
      const val = parseInt(input.value) || 1;
      input.value = Math.min(max, val + 1);
      input.dispatchEvent(new Event('change'));
    });
  });

  /* ──────────────────────────────────
     Add to Cart (AJAX)
  ────────────────────────────────── */
  document.querySelectorAll('.ajax-add-to-cart').forEach(form => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = form.querySelector('button[type="submit"]');
      const originalText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

      try {
        const res = await fetch(form.action, {
          method: 'POST',
          body: new FormData(form),
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await res.json();
        if (data.success) {
          // Update cart badge
          document.querySelectorAll('.cart-badge').forEach(badge => {
            badge.textContent = data.cart_count;
          });
          showToast('Added to cart! 🙏', 'success');
          btn.innerHTML = '✓ Added!';
          btn.style.background = '#28a745';
          setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.background = '';
            btn.disabled = false;
          }, 2000);
        }
      } catch (err) {
        showToast('Something went wrong. Try again.', 'danger');
        btn.innerHTML = originalText;
        btn.disabled = false;
      }
    });
  });

  /* ──────────────────────────────────
     Cart Page: Update on qty change
  ────────────────────────────────── */
  const cartForm = document.getElementById('cart-form');
  if (cartForm) {
    cartForm.querySelectorAll('input[name^="qty_"]').forEach(input => {
      let debounceTimer;
      input.addEventListener('change', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          // Recalculate line total
          const row = input.closest('tr');
          if (row) {
            const price = parseFloat(row.dataset.price || 0);
            const qty   = parseInt(input.value) || 1;
            const lineEl = row.querySelector('.line-total');
            if (lineEl) lineEl.textContent = `₹${(price * qty).toFixed(0)}`;
          }
        }, 300);
      });
    });
  }

  /* ──────────────────────────────────
     Payment method toggle
  ────────────────────────────────── */
  document.querySelectorAll('.payment-option input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.payment-option').forEach(opt => opt.classList.remove('selected'));
      radio.closest('.payment-option').classList.add('selected');
    });
    if (radio.checked) radio.closest('.payment-option').classList.add('selected');
  });

  /* ──────────────────────────────────
     Razorpay Payment
  ────────────────────────────────── */
  const rzpBtn = document.getElementById('rzp-pay-btn');
  if (rzpBtn) {
    rzpBtn.addEventListener('click', () => {
      const options = {
        key:            rzpBtn.dataset.key,
        amount:         rzpBtn.dataset.amount,
        currency:       'INR',
        name:           'ISKCON Book Store',
        description:    'Book Purchase',
        order_id:       rzpBtn.dataset.orderId,
        image:          '/static/images/logo.png',
        handler: async (response) => {
          // Verify payment on backend
          const formData = new FormData();
          formData.append('razorpay_order_id',   response.razorpay_order_id);
          formData.append('razorpay_payment_id',  response.razorpay_payment_id);
          formData.append('razorpay_signature',   response.razorpay_signature);
          formData.append('order_number',          rzpBtn.dataset.orderNumber);

          const res = await fetch('/payment/verify', {
            method: 'POST',
            body: formData,
          });
          const data = await res.json();
          window.location.href = data.redirect;
        },
        prefill: {
          name:    rzpBtn.dataset.name  || '',
          contact: rzpBtn.dataset.phone || '',
          email:   rzpBtn.dataset.email || '',
        },
        theme: { color: '#FF6600' },
        modal: {
          ondismiss: () => showToast('Payment cancelled.', 'warning'),
        }
      };
      new Razorpay(options).open();
    });
  }

  /* ──────────────────────────────────
     Search bar focus effect
  ────────────────────────────────── */
  const searchInput = document.querySelector('.search-input-nav');
  if (searchInput) {
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') searchInput.form.submit();
    });
  }

  /* ──────────────────────────────────
     Coupon code — uppercase input
  ────────────────────────────────── */
  document.querySelectorAll('input[name="coupon_code"]').forEach(input => {
    input.addEventListener('input', () => {
      const pos = input.selectionStart;
      input.value = input.value.toUpperCase();
      input.setSelectionRange(pos, pos);
    });
  });

  /* ──────────────────────────────────
     Smooth scroll to top button
  ────────────────────────────────── */
  const topBtn = document.getElementById('scroll-top-btn');
  if (topBtn) {
    window.addEventListener('scroll', () => {
      topBtn.style.display = window.scrollY > 300 ? 'flex' : 'none';
    });
    topBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

  /* ──────────────────────────────────
     Admin: Sidebar toggle (mobile)
  ────────────────────────────────── */
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const adminSidebar  = document.querySelector('.admin-sidebar');
  if (sidebarToggle && adminSidebar) {
    sidebarToggle.addEventListener('click', () => {
      adminSidebar.classList.toggle('show');
    });
  }

  /* ──────────────────────────────────
     Admin: Featured toggle
  ────────────────────────────────── */
  document.querySelectorAll('.featured-toggle').forEach(btn => {
    btn.addEventListener('click', async () => {
      const bookId = btn.dataset.bookId;
      const res = await fetch(`/admin/books/toggle-featured/${bookId}`, { method: 'POST' });
      const data = await res.json();
      btn.textContent  = data.featured ? '⭐ Featured' : '☆ Feature';
      btn.style.color  = data.featured ? 'var(--gold)' : '';
      showToast(data.featured ? 'Marked as featured!' : 'Removed from featured.', 'info');
    });
  });

  /* ──────────────────────────────────
     Image preview on file input
  ────────────────────────────────── */
  const imgInput = document.getElementById('book-image-input');
  const imgPreview = document.getElementById('book-image-preview');
  if (imgInput && imgPreview) {
    imgInput.addEventListener('change', () => {
      const file = imgInput.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          imgPreview.src = e.target.result;
          imgPreview.style.display = 'block';
        };
        reader.readAsDataURL(file);
      }
    });
  }

  /* ──────────────────────────────────
     WhatsApp order link builder
  ────────────────────────────────── */
  const waBtn = document.getElementById('whatsapp-order-btn');
  if (waBtn) {
    waBtn.addEventListener('click', () => {
      const orderNum = waBtn.dataset.order;
      const phone    = waBtn.dataset.phone;
      const message  = encodeURIComponent(
        `🙏 Hare Krishna!\nI'd like to check my order: ${orderNum}\nThank you.`
      );
      window.open(`https://wa.me/${phone.replace(/\D/g, '')}?text=${message}`, '_blank');
    });
  }

  console.log('🙏 Hare Krishna! ISKCON Book Store loaded.');
});
