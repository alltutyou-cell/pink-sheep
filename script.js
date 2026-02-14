// Get elements
const yesBtn = document.getElementById('yesBtn');
const noBtn = document.getElementById('noBtn');
const message = document.getElementById('message');

// Track "No" button click count
let noClickCount = 0;
let sheepClickCount = 0;
let isButtonRunning = false;
let lastMoveTime = 0;

// Messages for "No" button clicks
const noMessages = [
    "Are you sure? 🥺",
    "The sheep will be sad... 😢",
    "Please reconsider! 💔",
    "But... but... the sheep made cookies! 🍪",
    "They've been practicing their 'baa' just for you! 🎵",
    "Come on, just one chance? 🙏",
    "The sheep are crying now... 😭",
    "You're breaking their little hearts! 💔",
    "They bought you flowers! 🌹",
    "Fine, be that way... 😤"
];

// Handle "Yes" button click
yesBtn.addEventListener('click', function () {
    // Add celebration effect
    document.body.classList.add('celebration');

    // Update message
    message.innerHTML = "🎉 YAY! The sheep are so happy! 💕🐑";
    message.style.color = '#ff1493';
    message.style.fontSize = '2rem';

    // Make the Yes button even bigger
    yesBtn.style.transform = 'scale(1.3)';
    yesBtn.innerHTML = '💕 YES! 💕';

    // Hide No button
    noBtn.style.display = 'none';

    // Create confetti effect
    createConfetti();

    // Make all sheep jump for joy
    const allSheep = document.querySelectorAll('.sheep');
    allSheep.forEach((sheep, index) => {
        setTimeout(() => {
            sheep.style.animation = 'jumpForJoy 0.6s ease-in-out';
        }, index * 100);
    });

    // Remove celebration class after animation
    setTimeout(() => {
        document.body.classList.remove('celebration');
    }, 1500);
});

// Handle "No" button click
noBtn.addEventListener('click', function () {
    if (noClickCount < noMessages.length) {
        message.textContent = noMessages[noClickCount];
        message.style.color = '#ff69b4';

        // Make Yes button bigger and No button smaller
        const yesScale = 1 + (noClickCount * 0.15);
        const noScale = 1 - (noClickCount * 0.1);

        yesBtn.style.transform = `scale(${yesScale})`;
        noBtn.style.transform = `scale(${noScale})`;

        noClickCount++;

        // After many clicks, hide the No button
        if (noClickCount >= noMessages.length) {
            noBtn.style.opacity = '0';
            noBtn.style.pointerEvents = 'none';
            message.innerHTML = "Looks like 'Yes' is your only option now! 😊💕";
        }
    }
});

// Make the No button run away immediately!
noBtn.addEventListener('mouseenter', function (e) {
    if (!isButtonRunning) {
        runAwayFromCursor(e);
    }
});

// Also run away when cursor gets close (with throttling)
document.addEventListener('mousemove', function (e) {
    const now = Date.now();
    // Throttle: only check every 50ms
    if (now - lastMoveTime < 50) return;

    if (noBtn.style.opacity !== '0' && noBtn.style.display !== 'none') {
        const noBtnRect = noBtn.getBoundingClientRect();
        const noBtnCenterX = noBtnRect.left + noBtnRect.width / 2;
        const noBtnCenterY = noBtnRect.top + noBtnRect.height / 2;

        const distance = Math.sqrt(
            Math.pow(e.clientX - noBtnCenterX, 2) +
            Math.pow(e.clientY - noBtnCenterY, 2)
        );

        // If cursor is within 150px, run away!
        if (distance < 150) {
            runAwayFromCursor(e);
            lastMoveTime = now;
        }
    }
});

function runAwayFromCursor(e) {
    isButtonRunning = true;

    // Make button absolutely positioned so it can move freely
    if (noBtn.style.position !== 'fixed') {
        noBtn.style.position = 'fixed';
    }

    // Get viewport dimensions
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const btnWidth = noBtn.offsetWidth || 100;
    const btnHeight = noBtn.offsetHeight || 50;

    // Get current button position (or default to center if not set)
    const currentRect = noBtn.getBoundingClientRect();
    const currentX = currentRect.left;
    const currentY = currentRect.top;

    // Calculate direction away from cursor
    let deltaX = currentX - e.clientX;
    let deltaY = currentY - e.clientY;

    // If cursor is right on top (delta is 0), move randomly
    if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
        deltaX = Math.random() > 0.5 ? 10 : -10;
        deltaY = Math.random() > 0.5 ? 10 : -10;
    }

    // Normalize logic
    const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    const moveDistance = 200; // Move further away

    let newX = currentX + (deltaX / distance) * moveDistance;
    let newY = currentY + (deltaY / distance) * moveDistance;

    // Add randomness
    newX += (Math.random() - 0.5) * 50;
    newY += (Math.random() - 0.5) * 50;

    // Boundary checks with padding
    const padding = 20;

    // If hitting left/right wall, bounce back
    if (newX < padding) newX = padding + 20;
    if (newX > viewportWidth - btnWidth - padding) newX = viewportWidth - btnWidth - padding - 20;

    // If hitting top/bottom wall, bounce back
    if (newY < padding) newY = padding + 20;
    if (newY > viewportHeight - btnHeight - padding) newY = viewportHeight - btnHeight - padding - 20;

    // Apply new position with smooth transition
    noBtn.style.transition = 'all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1)';
    noBtn.style.left = newX + 'px';
    noBtn.style.top = newY + 'px';

    // Add a little shake animation
    noBtn.style.animation = 'shake 0.4s';
    setTimeout(() => {
        noBtn.style.animation = '';
        isButtonRunning = false;
    }, 400);
}

// Sheep Easter Egg: Click them to make them Baa!
const sheepElements = document.querySelectorAll('.sheep, .main-sheep');
sheepElements.forEach(sheep => {
    sheep.addEventListener('click', function (e) {
        sheepClickCount++;

        // Create "Baa!" text
        const baa = document.createElement('div');
        baa.textContent = "Baa! 🐑";
        baa.style.position = 'fixed';
        baa.style.left = e.clientX + 'px';
        baa.style.top = e.clientY + 'px';
        baa.style.color = '#ff69b4';
        baa.style.fontWeight = 'bold';
        baa.style.fontSize = '1.5rem';
        baa.style.pointerEvents = 'none';
        baa.style.zIndex = '1000';
        baa.style.animation = 'floatUp 1s ease-out forwards';
        document.body.appendChild(baa);

        // Remove text after animation
        setTimeout(() => baa.remove(), 1000);

        // Bounce the sheep
        this.style.transform = 'scale(1.2) translateY(-20px)';
        setTimeout(() => {
            this.style.transform = 'scale(1) translateY(0)';
        }, 200);

        // Mega Secret: if clicked enough times
        if (sheepClickCount === 10) {
            message.textContent = "You really like sheep! 🐑💕";
            createConfetti();
        }
    });
});

// Move No button to random position
function moveNoButton() {
    const container = document.querySelector('.button-container');
    const containerRect = container.getBoundingClientRect();

    const maxX = containerRect.width - noBtn.offsetWidth;
    const maxY = containerRect.height - noBtn.offsetHeight;

    const randomX = Math.random() * maxX;
    const randomY = Math.random() * maxY;

    noBtn.style.position = 'absolute';
    noBtn.style.left = randomX + 'px';
    noBtn.style.top = randomY + 'px';
}

// Create confetti effect
function createConfetti() {
    const colors = ['#ff69b4', '#ff1493', '#ffb6d9', '#ffd9ec', '#ffffff'];
    const confettiCount = 50;

    for (let i = 0; i < confettiCount; i++) {
        setTimeout(() => {
            const confetti = document.createElement('div');
            confetti.style.position = 'fixed';
            confetti.style.width = '10px';
            confetti.style.height = '10px';
            confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            confetti.style.left = Math.random() * 100 + '%';
            confetti.style.top = '-10px';
            confetti.style.borderRadius = Math.random() > 0.5 ? '50%' : '0';
            confetti.style.opacity = '1';
            confetti.style.zIndex = '1000';
            confetti.style.pointerEvents = 'none';

            document.body.appendChild(confetti);

            // Animate confetti falling
            const duration = 2000 + Math.random() * 2000;
            const rotation = Math.random() * 360;
            const xMovement = (Math.random() - 0.5) * 200;

            confetti.animate([
                {
                    transform: 'translateY(0) translateX(0) rotate(0deg)',
                    opacity: 1
                },
                {
                    transform: `translateY(${window.innerHeight + 20}px) translateX(${xMovement}px) rotate(${rotation}deg)`,
                    opacity: 0
                }
            ], {
                duration: duration,
                easing: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)'
            });

            // Remove confetti after animation
            setTimeout(() => {
                confetti.remove();
            }, duration);
        }, i * 30);
    }
}

// Floating Photos Feature
const photoContainer = document.createElement('div');
photoContainer.className = 'photo-container';
document.body.appendChild(photoContainer);

// Configuration - easily add more here!
const totalPhotos = 27; // Try files 1.jpg to 10.jpg
const photoFolder = 'photos/';

function createFloatingPhoto() {
    // Pick a random photo number
    const randomNum = Math.floor(Math.random() * totalPhotos) + 1;
    const imgSrc = `${photoFolder}${randomNum}.jpg`;

    // Create element
    const photoDiv = document.createElement('div');
    photoDiv.className = 'floating-photo';

    // Random positioning and movement variables
    const startLeft = Math.random() * 90; // 0-90% width
    const duration = 15 + Math.random() * 10; // 15-25s float time
    const rotation = (Math.random() - 0.5) * 30; // -15 to +15 deg
    const endRotation = rotation + (Math.random() - 0.5) * 60; // Drifts rotation
    const drift = (Math.random() - 0.5) * 200; // Drifts left/right by up to 100px

    // Apply styles
    photoDiv.style.left = startLeft + '%';
    photoDiv.style.animationDuration = duration + 's';
    photoDiv.style.setProperty('--rotation', rotation + 'deg');
    photoDiv.style.setProperty('--end-rotation', endRotation + 'deg');
    photoDiv.style.setProperty('--drift', drift + 'px');

    // Image element
    const img = document.createElement('img');
    img.src = imgSrc;
    img.alt = 'Cute memory';

    // Only append if image loads successfully
    img.onload = function () {
        photoDiv.appendChild(img);
        document.body.appendChild(photoDiv);

        // Remove after animation completes
        setTimeout(() => {
            photoDiv.remove();
        }, duration * 1000);
    };

    img.onerror = function () {
        // If image doesn't exist, maybe try the placeholder for demo
        if (Math.random() < 0.1) { // 10% chance to show placeholder instead
            img.src = 'photos/placeholder.jpg';
        }
    };
}

// Start creating photos every few seconds
setInterval(createFloatingPhoto, 3000);

// Add jump animation
const style = document.createElement('style');
style.textContent = `
    @keyframes jumpForJoy {
        0%, 100% { transform: translateY(0) rotate(0deg); }
        50% { transform: translateY(-30px) rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Add hover effect to sheep
const allSheep = document.querySelectorAll('.sheep');
allSheep.forEach(sheep => {
    sheep.addEventListener('mouseenter', function () {
        this.style.transform = 'scale(1.2)';
        this.style.transition = 'transform 0.3s ease';
    });

    sheep.addEventListener('mouseleave', function () {
        this.style.transform = 'scale(1)';
    });
});
