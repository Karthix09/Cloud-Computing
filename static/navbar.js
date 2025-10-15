// static/navbar.js
export function createSidebar(current) {
  const html = `
    <style>
      /* ============================
         Sidebar & Hover Drawer Styles
      ============================ */

      /* Small invisible edge to trigger the drawer */
      #hover-edge {
        position: fixed;
        left: 0;
        top: 0;
        width: 12px;
        height: 100vh;
        z-index: 9998; /* below the sidebar itself */
      }

      /* Off-canvas drawer */
      .app-sidebar {
        position: fixed;
        top: 0;
        left: 0;
        width: 230px;
        height: 100vh;
        background: #111827;
        color: #fff;
        display: flex;
        flex-direction: column;
        padding-top: 20px;
        box-shadow: 2px 0 8px rgba(0, 0, 0, 0.35);
        transform: translateX(-100%); /* completely off-screen */
        transition: transform 0.25s ease;
        z-index: 9999; /* always above map */
        pointer-events: none; /* don't capture clicks while hidden */
      }

      /* Reveal when hovering edge or sidebar itself */
      #hover-edge:hover + .app-sidebar,
      .app-sidebar:hover {
        transform: translateX(0);
        pointer-events: auto;
      }

      /* Sidebar header */
      .app-sidebar h2 {
        text-align: center;
        margin-bottom: 24px;
        color: #3b82f6;
        font-size: 18px;
      }

      /* Sidebar links */
      .app-sidebar a {
        text-decoration: none;
        color: #d1d5db;
        padding: 12px 24px;
        display: block;
        font-size: 15px;
        transition: background 0.2s, color 0.2s;
      }

      .app-sidebar a:hover,
      .app-sidebar a.active {
        background: #2563eb;
        color: #fff;
      }

      /* Shift main content when drawer is open */
      #hover-edge:hover ~ .content,
      .app-sidebar:hover ~ .content {
        margin-left: 230px;
        transition: margin-left 0.25s ease;
      }

      /* Ensure Leaflet map stays below sidebar */
      .leaflet-container {
        z-index: 1 !important;
      }
    </style>

    <div id="hover-edge"></div>

    <nav class="app-sidebar">
      <h2>Transport Analytics Hub</h2>
    
<a href="http://127.0.0.1:5000" class="${
        current === 'bus' ? 'active' : ''
      }">🚍 Bus Dashboard</a>
      <a href="http://127.0.0.1:5001" class="${
        current === 'traffic' ? 'active' : ''
      }">🚧 Traffic Dashboard</a>
      <a href="/settings">⚙️ Settings</a>
      <a href="/logout">↩︎ Logout</a>
    </nav>
  `;

  document.body.insertAdjacentHTML('afterbegin', html);
}



      //   <a href="/bus" class="${
      //   current === 'bus' ? 'active' : ''
      // }">🚍 Bus Dashboard</a>
      // <a href="/traffic" class="${
      //   current === 'traffic' ? 'active' : ''
      // }">🚧 Traffic Dashboard</a>
