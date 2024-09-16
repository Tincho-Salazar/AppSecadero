document.addEventListener('DOMContentLoaded', function() {
    function showToast(message, type) {
        let toastTemplate = document.getElementById('toastTemplate');
        let toast = toastTemplate.cloneNode(true);
        toast.id = '';
        toast.style.display = 'block';
        
        let toastBody = toast.querySelector('.toast-body');
        
        // Ensure toast background is always white
        toast.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-primary');
        toast.classList.add('bg-white', 'bg-' + type); // Set toast background color

        // Add icon based on type
        if (type === 'success') {
            toastBody.innerHTML = '<i class="bi bi-check-circle text-success"></i> ' + message;
        } else if (type === 'danger') {
            toastBody.innerHTML = '<i class="bi bi-x-circle text-danger"></i> ' + message;
        } else if (type === 'warning') {
            toastBody.innerHTML = '<i class="bi bi-exclamation-circle text-warning"></i> ' + message;
        }

        // Add progress bar
        let progressBar = document.createElement('div');
        progressBar.classList.add('toast-progress');
        toast.appendChild(progressBar);

        let toastContainer = document.getElementById('toastContainer');
        toastContainer.appendChild(toast);

        let bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        // Remove the toast after it hides
        toast.addEventListener('hidden.bs.toast', function() {
            toast.remove();
        });

        // Animate progress bar
        setTimeout(() => {
            progressBar.style.animationDuration = '5s'; // Adjust duration as needed
            progressBar.style.animationPlayState = 'running';
        }, 100);

        return bsToast;
    }

    // Attach showToast function to the global window object
    window.showToast = showToast;
});
