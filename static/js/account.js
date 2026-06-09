/**
 * Account management page handlers
 * - Change password
 * - Delete account
 * - Logout
 */

(function () {
    'use strict';

    // --- Change Password ---
    var changePwForm = document.getElementById('change-password-form');
    if (changePwForm) {
        // Password strength meter
        var newPwInput = document.getElementById('new-password');
        if (newPwInput) {
            newPwInput.addEventListener('input', function () {
                updateStrength(this.value, 'strength-bar-change', 'strength-text-change');
                checkConfirmMatch();
            });
        }

        var confirmInput = document.getElementById('new-password-confirm');
        if (confirmInput) {
            confirmInput.addEventListener('input', checkConfirmMatch);
        }

        changePwForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            var currentPassword = document.getElementById('current-password').value;
            var newPassword = newPwInput.value;
            var newConfirm = confirmInput.value;
            var msgEl = document.getElementById('password-message');

            // Validate
            if (!currentPassword) {
                showFieldError('current-password', '请输入当前密码');
                return;
            }
            if (newPassword.length < 8) {
                showFieldError('new-password', '新密码至少8位');
                return;
            }
            if (newPassword !== newConfirm) {
                showFieldError('new-password-confirm', '两次输入的新密码不一致');
                return;
            }
            if (currentPassword === newPassword) {
                showFieldError('new-password', '新密码不能与当前密码相同');
                return;
            }

            try {
                var resp = await apiFetch('/auth/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: currentPassword,
                        new_password: newPassword,
                        new_password_confirm: newConfirm,
                    }),
                });

                var result = await resp.json();

                msgEl.className = 'form-message';
                if (resp.ok) {
                    msgEl.classList.add('success');
                    msgEl.textContent = result.message || '密码修改成功。';
                    changePwForm.reset();
                } else {
                    msgEl.classList.add('error');
                    msgEl.textContent = result.error || '修改失败。';
                }
            } catch (err) {
                msgEl.className = 'form-message error';
                msgEl.textContent = '网络错误，请稍后重试。';
            }
        });
    }

    function checkConfirmMatch() {
        var newPw = document.getElementById('new-password').value;
        var confirm = document.getElementById('new-password-confirm').value;
        var err = document.getElementById('new-password-confirm-error');
        if (err && confirm && newPw !== confirm) {
            err.textContent = '两次输入的新密码不一致';
            err.classList.add('visible');
        } else if (err) {
            err.classList.remove('visible');
        }
    }

    // --- Delete Account ---
    var deleteForm = document.getElementById('delete-account-form');
    if (deleteForm) {
        deleteForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            var password = document.getElementById('delete-password').value;
            var msgEl = document.getElementById('delete-message');

            if (!password) {
                showFieldError('delete-password', '请输入密码');
                return;
            }

            // Double confirmation
            if (!confirm('确定要注销账号吗？此操作不可撤销！\n\n请再次确认。')) {
                return;
            }

            try {
                var resp = await apiFetch('/auth/delete-account', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: password }),
                });

                var result = await resp.json();

                if (resp.ok && result.redirect) {
                    window.location.href = result.redirect;
                } else {
                    msgEl.className = 'form-message error';
                    msgEl.textContent = result.error || '注销失败。';
                }
            } catch (err) {
                msgEl.className = 'form-message error';
                msgEl.textContent = '网络错误，请稍后重试。';
            }
        });
    }

    // --- Logout ---
    var logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async function () {
            try {
                var resp = await apiFetch('/auth/logout', { method: 'POST' });
                var result = await resp.json();
                if (result.redirect) {
                    window.location.href = result.redirect;
                }
            } catch (err) {
                console.error('Logout failed:', err);
            }
        });
    }

    // --- Helpers ---
    function showFieldError(inputId, message) {
        var err = document.getElementById(inputId + '-error');
        if (err) {
            err.textContent = message;
            err.classList.add('visible');
        }
    }

    function updateStrength(password, barId, textId) {
        var bar = document.getElementById(barId);
        var text = document.getElementById(textId);
        if (!bar || !text) return;

        var score = 0;
        if (password.length >= 8) score++;
        if (/[A-Z]/.test(password)) score++;
        if (/[a-z]/.test(password)) score++;
        if (/[0-9]/.test(password)) score++;
        if (/[^A-Za-z0-9]/.test(password)) score++;

        bar.className = 'strength-bar';
        if (score <= 1 && password.length > 0) {
            bar.classList.add('weak');
            text.textContent = '密码强度：弱';
        } else if (score === 2) {
            bar.classList.add('fair');
            text.textContent = '密码强度：一般';
        } else if (score === 3) {
            bar.classList.add('good');
            text.textContent = '密码强度：良好';
        } else if (score >= 4) {
            bar.classList.add('strong');
            text.textContent = '密码强度：强';
        } else {
            text.textContent = '密码强度';
        }
    }
})();
