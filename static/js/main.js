/* ─── Navigation ─────────────────────────────────────────── */
const navWrapper = document.querySelector('.nav-wrapper');
const navbar = document.querySelector('.navbar');
const hamburger = document.querySelector('.nav-hamburger');
const mobileNav = document.querySelector('.nav-mobile');

// Scroll-based navbar style
window.addEventListener('scroll', () => {
  if (window.scrollY > 60) {
    navbar && navbar.classList.add('scrolled');
  } else {
    navbar && navbar.classList.remove('scrolled');
  }
});

// Mobile hamburger toggle
if (hamburger && mobileNav) {
  hamburger.addEventListener('click', () => {
    hamburger.classList.toggle('open');
    mobileNav.classList.toggle('open');
    navbar && navbar.classList.toggle('mobile-open');
  });
  // Close on link click
  mobileNav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      hamburger.classList.remove('open');
      mobileNav.classList.remove('open');
      navbar && navbar.classList.remove('mobile-open');
    });
  });
}

// Active nav link
const currentPath = window.location.pathname;
document.querySelectorAll('.nav-links a, .nav-mobile a').forEach(link => {
  const href = link.getAttribute('href');
  if (href === currentPath || (currentPath === '/' && href === '/')) {
    link.classList.add('active');
  } else if (href !== '/' && currentPath.startsWith(href)) {
    link.classList.add('active');
  }
});


/* ─── Scroll Reveal (Intersection Observer) ─────────────── */
const revealEls = document.querySelectorAll('.reveal, .reveal-left, .reveal-right');
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

revealEls.forEach(el => revealObserver.observe(el));


/* ─── Counter Animation (Trust Bar) ─────────────────────── */
function animateCounter(el) {
  const target = parseInt(el.dataset.target, 10);
  const suffix = el.dataset.suffix || '';
  const duration = 2000;
  const step = Math.ceil(target / (duration / 16));
  let current = 0;

  const timer = setInterval(() => {
    current = Math.min(current + step, target);
    el.textContent = current.toLocaleString() + suffix;
    if (current >= target) clearInterval(timer);
  }, 16);
}

const counters = document.querySelectorAll('.trust-number[data-target]');
if (counters.length > 0) {
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        counterObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });
  counters.forEach(c => counterObserver.observe(c));
}


/* ─── FAQ Accordion ──────────────────────────────────────── */
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    const item = btn.closest('.faq-item');
    const answer = item.querySelector('.faq-answer');
    const isOpen = item.classList.contains('open');

    // Close all
    document.querySelectorAll('.faq-item.open').forEach(openItem => {
      openItem.classList.remove('open');
      openItem.querySelector('.faq-answer').style.maxHeight = '0';
    });

    // Toggle clicked
    if (!isOpen) {
      item.classList.add('open');
      answer.style.maxHeight = answer.scrollHeight + 'px';
    }
  });
});


/* ─── Flash Message Auto-Dismiss ────────────────────────── */
document.querySelectorAll('.flash-msg').forEach(msg => {
  setTimeout(() => {
    msg.style.opacity = '0';
    msg.style.transform = 'translateX(40px)';
    msg.style.transition = '0.4s ease';
    setTimeout(() => msg.remove(), 400);
  }, 5000);
});


/* ─── Hero BG Pan on Load ────────────────────────────────── */
const heroBg = document.querySelector('.hero-bg');
if (heroBg) {
  setTimeout(() => heroBg.classList.add('loaded'), 100);
}


/* ─── Product Filter (Products page JS filter fallback) ─── */
// Server-side filtering is primary; this handles instant UI feedback
const filterTabs = document.querySelectorAll('.filter-tab[data-filter]');
filterTabs.forEach(tab => {
  tab.addEventListener('click', (e) => {
    filterTabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
  });
});


/* ─── Smooth hover lift reset on mobile ─────────────────── */
if ('ontouchstart' in window) {
  document.querySelectorAll('.product-card, .why-card, .value-card').forEach(card => {
    card.style.transition = 'box-shadow 0.3s ease';
  });
}


/* ─── Profile Dropdown Toggle ────────────────────────────── */
const profileToggle = document.getElementById('profile-toggle');
const profileDropdown = document.getElementById('profile-dropdown');
if (profileToggle && profileDropdown) {
  profileToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const isExpanded = profileToggle.getAttribute('aria-expanded') === 'true';
    profileToggle.setAttribute('aria-expanded', !isExpanded);
    profileDropdown.style.display = isExpanded ? 'none' : 'flex';
    const arrowIcon = profileToggle.querySelector('.arrow-icon');
    if (arrowIcon) {
      arrowIcon.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(180deg)';
    }
  });

  document.addEventListener('click', (e) => {
    if (!profileToggle.contains(e.target) && !profileDropdown.contains(e.target)) {
      profileToggle.setAttribute('aria-expanded', 'false');
      profileDropdown.style.display = 'none';
      const arrowIcon = profileToggle.querySelector('.arrow-icon');
      if (arrowIcon) {
        arrowIcon.style.transform = 'rotate(0deg)';
      }
    }
  });
}
