// static/navbar.js
export function createSidebar(current) {
  console.log("createSidebar called with:", current);

  const html = `
    <style>
      /* ============================
         Hamburger Menu Button
      ============================ */
      .hamburger-btn {
        position: fixed;
        top: 20px;
        left: 20px;
        width: 50px;
        height: 50px;
        background: #111827;
        border: none;
        border-radius: 10px;
        cursor: pointer;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        gap: 6px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
      }

      .hamburger-btn:hover {
        background: #1f2937;
        transform: scale(1.05);
      }

      .hamburger-btn span {
        width: 26px;
        height: 3px;
        background: white;
        border-radius: 2px;
        transition: all 0.3s ease;
      }

      /* Animate hamburger to X when open */
      .hamburger-btn.open span:nth-child(1) {
        transform: rotate(45deg) translate(8px, 8px);
      }

      .hamburger-btn.open span:nth-child(2) {
        opacity: 0;
      }

      .hamburger-btn.open span:nth-child(3) {
        transform: rotate(-45deg) translate(7px, -7px);
      }

      /* ============================
         Sidebar Styles
      ============================ */
      .app-sidebar {
        position: fixed;
        top: 0;
        left: 0;
        width: 260px;
        height: 100vh;
        background: linear-gradient(180deg, #111827 0%, #1f2937 100%);
        color: #fff;
        display: flex;
        flex-direction: column;
        padding-top: 80px;
        box-shadow: 4px 0 15px rgba(0, 0, 0, 0.4);
        transform: translateX(-100%);
        transition: transform 0.3s ease;
        z-index: 9999;
      }

      .app-sidebar.open {
        transform: translateX(0);
      }

      /* Sidebar header */
      .app-sidebar h2 {
        text-align: center;
        margin-bottom: 30px;
        padding: 0 20px;
        color: #60a5fa;
        font-size: 19px;
        font-weight: 600;
        letter-spacing: 0.5px;
      }

      /* Sidebar links */
      .app-sidebar a {
        text-decoration: none;
        color: #d1d5db;
        padding: 16px 28px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 15px;
        font-weight: 500;
        transition: all 0.2s ease;
        border-left: 4px solid transparent;
      }

      .app-sidebar a:hover {
        background: rgba(59, 130, 246, 0.1);
        color: #fff;
        border-left-color: #3b82f6;
      }

      .app-sidebar a.active {
        background: rgba(59, 130, 246, 0.2);
        color: #fff;
        border-left-color: #60a5fa;
        font-weight: 600;
      }

      /* Overlay for mobile */
      .sidebar-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.5);
        z-index: 9998;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.3s ease;
      }

      .sidebar-overlay.open {
        opacity: 1;
        pointer-events: auto;
      }

      /* Content shift on desktop */
      @media (min-width: 768px) {
        .content {
          transition: margin-left 0.3s ease;
        }

        .content.shifted {
          margin-left: 260px;
        }
      }

      /* Ensure Leaflet map stays below sidebar */
      .leaflet-container {
        z-index: 1 !important;
      }

      /* Footer section in sidebar */
      .sidebar-footer {
        margin-top: auto;
        padding: 20px 28px;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        font-size: 13px;
        color: #9ca3af;
        text-align: center;
      }
    </style>

    <!-- Hamburger Button -->
    <button class="hamburger-btn" id="hamburgerBtn" aria-label="Toggle Menu">
      <span></span>
      <span></span>
      <span></span>
    </button>

    <!-- Overlay (for mobile) -->
    <div class="sidebar-overlay" id="sidebarOverlay"></div>

    <!-- Sidebar -->
    <nav class="app-sidebar" id="appSidebar">
      <h2>🚀 Transport Analytics</h2>
      
          <a href="/bus" class="${current === 'bus' ? 'active' : ''}">
        <span>🚌</span>
        <span>Bus Dashboard</span>
      </a>

      <a href="/traffic" class="${current === 'traffic' ? 'active' : ''}">
        <span>🚧</span>
        <span>Traffic Dashboard</span>
      </a>

     <a href="/chatbot" class="${current === 'chatbot' ? 'active' : ''}">
    <span>🤖</span>
    <span>AI Assistant</span>
     </a>
      <a href="/charts" class="${current === 'charts' ? 'active' : ''}">
        <span>📊</span>
        <span>Analytics Dashboard</span>
      </a>
      <a href="/settings" class="${current === 'settings' ? 'active' : ''}">
        <span>⚙️</span>
        <span>Settings</span>
      </a>
      
      <a href="/logout">
        <span>🚪</span>
        <span>Logout</span>
      </a>


      <div class="sidebar-footer">
        Transport Analytics Hub<br>
        v1.0
      </div>
    </nav>
  `;

  document.body.insertAdjacentHTML('afterbegin', html);
  console.log("HTML inserted into DOM");

  // Get elements
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('appSidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const content = document.querySelector('.content');

  console.log("Elements found:", {
    hamburgerBtn: !!hamburgerBtn,
    sidebar: !!sidebar,
    overlay: !!overlay,
    content: !!content
  });

  // Toggle sidebar function
  function toggleSidebar() {
    hamburgerBtn.classList.toggle('open');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');

    // Shift content on desktop only
    if (window.innerWidth >= 768 && content) {
      content.classList.toggle('shifted');
    }
  }

  // Event listeners
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', toggleSidebar);
    console.log("Hamburger button listener attached");
  }

  if (overlay) {
    overlay.addEventListener('click', toggleSidebar);
  }

  // Close sidebar when clicking a link (mobile)
  if (sidebar) {
    const sidebarLinks = sidebar.querySelectorAll('a');
    sidebarLinks.forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth < 768) {
          toggleSidebar();
        }
      });
    });
  }

  // Handle window resize
  window.addEventListener('resize', () => {
    if (window.innerWidth >= 768 && overlay) {
      overlay.classList.remove('open');
    }
  });

  // Close sidebar with Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar && sidebar.classList.contains('open')) {
      toggleSidebar();
    }
  });

  console.log("Sidebar setup complete!");
}