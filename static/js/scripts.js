// Fetch Suggested Restaurant
document.addEventListener("DOMContentLoaded", function () {
    const suggestedDiv = document.getElementById("suggested-restaurant");

    if (suggestedDiv) {
        fetch("/suggested-restaurant")
            .then(response => response.json())
            .then(data => {
                if (data && data.name) {
                    suggestedDiv.innerHTML = `
                        <div class="alert alert-info mt-3">
                            <strong>Suggestion:</strong> Try <strong>${data.name}</strong> at ${data.location}. It's currently the least crowded!
                        </div>
                    `;
                } else {
                    suggestedDiv.innerHTML = `
                        <div class="alert alert-warning mt-3">
                            No suggestions available at the moment.
                        </div>
                    `;
                }
            })
            .catch(err => {
                console.error("Error fetching suggested restaurant:", err);
                suggestedDiv.innerHTML = `
                    <div class="alert alert-danger mt-3">
                        Could not load suggestions.
                    </div>
                `;
            });
    }

    // Auto-focus first input
    const firstInput = document.querySelector("form input, form select");
    if (firstInput) {
        firstInput.focus();
    }

    // Booking confirmation
    const bookingForm = document.querySelector("#booking-form");
    if (bookingForm) {
        bookingForm.addEventListener("submit", function (e) {
            const confirmBooking = confirm("Are you sure you want to confirm this reservation?");
            if (!confirmBooking) {
                e.preventDefault();
            }
        });
    }
});
