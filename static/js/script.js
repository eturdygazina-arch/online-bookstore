document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        document.querySelectorAll('.alert').forEach(function(alert) {
            try { new bootstrap.Alert(alert).close(); } catch(e) {}
        });
    }, 4500);

    const curtain = document.getElementById('pageCurtain');
    document.querySelectorAll('a[href]').forEach(link => {
        const href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:') || link.target === '_blank') return;
        link.addEventListener('click', function(e) {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            try {
                const url = new URL(href, window.location.href);
                if (url.origin !== window.location.origin) return;
            } catch(err) { return; }
            if (curtain) {
                e.preventDefault();
                curtain.classList.add('active');
                setTimeout(() => { window.location.href = href; }, 180);
            }
        });
    });

    const cards = document.querySelectorAll('.book-card, .genre-card, .publisher-card, .language-card');
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, {threshold: 0.1, rootMargin: '0px 0px -50px 0px'});
    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'all .45s ease-out';
        observer.observe(card);
    });

    document.querySelectorAll('.delete-confirm').forEach(btn => {
        btn.addEventListener('click', e => { if (!confirm('Өшіру керек пе?')) e.preventDefault(); });
    });

    if (!localStorage.getItem('zeinCountrySeen')) {
        const modalEl = document.getElementById('countryModal');
        if (modalEl) {
            setTimeout(() => {
                try { new bootstrap.Modal(modalEl).show(); localStorage.setItem('zeinCountrySeen', '1'); } catch(e) {}
            }, 900);
        }
    }
    if (!localStorage.getItem('zeinDiscountSeen')) {
        const discountEl = document.getElementById('welcomeDiscountModal');
        if (discountEl) {
            setTimeout(() => {
                try { new bootstrap.Modal(discountEl).show(); localStorage.setItem('zeinDiscountSeen', '1'); } catch(e) {}
            }, 2200);
        }
    }
});


function formatCardInputsFinal(){
  const card = document.querySelector('input[name="card_number"]');
  if(card){ card.addEventListener('input',()=>{card.value=card.value.replace(/\D/g,'').slice(0,16).replace(/(.{4})/g,'$1 ').trim();}); }
  const exp = document.querySelector('input[name="expiry"]');
  if(exp){ exp.addEventListener('input',()=>{let v=exp.value.replace(/\D/g,'').slice(0,4); if(v.length>2)v=v.slice(0,2)+'/'+v.slice(2); exp.value=v;}); }
}
document.addEventListener('DOMContentLoaded', formatCardInputsFinal);


document.addEventListener('DOMContentLoaded', function(){
  const useCert = document.getElementById('useCertificate');
  const certBox = document.getElementById('certificateBox');
  const certBtn = document.getElementById('checkCertificateBtn');
  const certCode = document.getElementById('certificateCode');
  const certResult = document.getElementById('certificateResult');
  const totalEl = document.getElementById('checkoutTotal');
  if(useCert && certBox){
    useCert.addEventListener('change', ()=>{ certBox.classList.toggle('d-none', !useCert.checked); if(!useCert.checked && certCode){certCode.value=''; if(certResult) certResult.innerHTML='';} });
  }
  if(certBtn && certCode && certResult){
    certBtn.addEventListener('click', async ()=>{
      const subtotal = totalEl ? totalEl.dataset.subtotal : 0;
      const code = certCode.value.trim().toUpperCase();
      if(!code){ certResult.innerHTML='<span class="text-danger">Код енгізіңіз</span>'; return; }
      try{
        const res = await fetch(`/api/check_certificate?code=${encodeURIComponent(code)}&subtotal=${subtotal}`);
        const data = await res.json();
        if(data.ok){ certResult.innerHTML=`<span class="text-success">Сертификат табылды: баланс ${Number(data.balance).toLocaleString('ru-RU')} ₸. Осы тапсырыстан ${Number(data.discount).toLocaleString('ru-RU')} ₸ шегеріледі.</span>`; }
        else { certResult.innerHTML=`<span class="text-danger">${data.message}</span>`; }
      }catch(e){ certResult.innerHTML='<span class="text-danger">Тексеру кезінде қате шықты</span>'; }
    });
  }
});
