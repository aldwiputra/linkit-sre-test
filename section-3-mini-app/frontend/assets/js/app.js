      // ── CONFIG ────────────────────────────────────────────────────────────────────
      const API = "http://localhost:8383/api";
      const AUTH_STORAGE_KEY = "cinevault.auth.token";
      const USER_STORAGE_KEY = "cinevault.auth.user";

      // ── STATE ─────────────────────────────────────────────────────────────────────
      let token = null,
        currentUser = null;
      let moviesPage = 1,
        moviesTotal = 0,
        moviesPages = 1;
      let searchTimeout = null;
      let editMovieId = null;

      // ── UTILS ─────────────────────────────────────────────────────────────────────
      const $ = (id) => document.getElementById(id);
      const show = (id) => $(id).classList.remove("hidden");
      const hide = (id) => $(id).classList.add("hidden");

      function saveAuthState() {
        if (token) localStorage.setItem(AUTH_STORAGE_KEY, token);
        if (currentUser)
          localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(currentUser));
      }

      function clearAuthState() {
        token = null;
        currentUser = null;
        localStorage.removeItem(AUTH_STORAGE_KEY);
        localStorage.removeItem(USER_STORAGE_KEY);
      }

      function showAuthenticatedApp() {
        $("sidebar-username").textContent = currentUser?.username || "User";
        hide("login-page");
        show("app");
        showPage("dashboard");
      }

      async function restoreAuthState() {
        const savedToken = localStorage.getItem(AUTH_STORAGE_KEY);
        if (!savedToken) return;

        token = savedToken;
        const savedUser = localStorage.getItem(USER_STORAGE_KEY);
        if (savedUser) {
          try {
            currentUser = JSON.parse(savedUser);
          } catch (_) {
            currentUser = null;
          }
        }

        const me = await api("GET", "/auth/me");
        if (!me.ok || !me.data?.data) {
          clearAuthState();
          return;
        }

        currentUser = me.data.data;
        saveAuthState();
        showAuthenticatedApp();
      }

      function toast(msg, type = "success") {
        const el = $("toast");
        el.textContent = msg;
        el.className = `show ${type}`;
        setTimeout(() => {
          el.className = "";
        }, 3000);
      }

      async function api(method, path, body) {
        const opts = {
          method,
          headers: { "Content-Type": "application/json" },
        };
        if (token) opts.headers["Authorization"] = `Bearer ${token}`;
        if (body) opts.body = JSON.stringify(body);
        try {
          const r = await fetch(API + path, opts);
          const d = await r.json();
          return { ok: r.ok, status: r.status, data: d };
        } catch (e) {
          return {
            ok: false,
            status: 0,
            data: { message: "Network error — is the backend running?" },
          };
        }
      }

      function fmtDate(iso) {
        return new Date(iso).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }

      function statusBadge(s) {
        const map = {
          watching: "badge-watching",
          watched: "badge-watched",
          want_to_watch: "badge-want",
          dropped: "badge-dropped",
        };
        const lbl = {
          watching: "Watching",
          watched: "Watched",
          want_to_watch: "Want",
          dropped: "Dropped",
        };
        return `<span class="badge ${map[s] || ""}">${lbl[s] || s}</span>`;
      }

      function stars(n) {
        if (!n) return '<span style="color:var(--muted)">—</span>';
        return `<span class="stars">${"★".repeat(n)}${"☆".repeat(10 - n)}</span>`;
      }

      // ── LOGIN ─────────────────────────────────────────────────────────────────────
      $("login-btn").onclick = doLogin;
      $("login-pass").onkeydown = (e) => {
        if (e.key === "Enter") doLogin();
      };

      async function doLogin() {
        hide("login-error");
        const username = $("login-user").value.trim();
        const password = $("login-pass").value;
        if (!username || !password) {
          showLoginErr("Please enter credentials");
          return;
        }
        $("login-btn").textContent = "Signing in…";
        const r = await api("POST", "/auth/login", { username, password });
        $("login-btn").textContent = "Sign In →";
        if (!r.ok) {
          showLoginErr(r.data.message || "Login failed");
          return;
        }
        token = r.data.data.access_token;
        currentUser = r.data.data.user;
        saveAuthState();
        showAuthenticatedApp();
      }

      function showLoginErr(msg) {
        const el = $("login-error");
        el.textContent = msg;
        show("login-error");
      }

      $("logout-btn").onclick = () => {
        clearAuthState();
        hide("app");
        show("login-page");
        $("login-pass").value = "";
      };

      // ── NAVIGATION ────────────────────────────────────────────────────────────────
      document.querySelectorAll(".nav-item").forEach((el) => {
        el.onclick = () => showPage(el.dataset.page);
      });

      const PAGE_TITLES = {
        dashboard: "Dashboard",
        movies: "Movies",
        watchlist: "My Watchlist",
        health: "System Health",
      };

      function showPage(name) {
        document.querySelectorAll(".nav-item").forEach((el) => {
          el.classList.toggle("active", el.dataset.page === name);
        });
        document
          .querySelectorAll(".page")
          .forEach((el) => el.classList.add("hidden"));
        $(`page-${name}`).classList.remove("hidden");
        $("topbar-title").textContent = PAGE_TITLES[name] || name;
        if (name === "dashboard") loadDashboard();
        if (name === "movies") loadMovies(1);
        if (name === "watchlist") loadWatchlist();
        if (name === "health") loadHealth();
      }

      // ── DASHBOARD ────────────────────────────────────────────────────────────────
      async function loadDashboard() {
        const [health, wl] = await Promise.all([
          api("GET", "/health"),
          api("GET", "/watchlist/"),
        ]);

        // stats
        if (health.ok) {
          const h = health.data;
          $("stat-health").textContent = h.status === "healthy" ? "✓" : "✗";
          $("stat-uptime").textContent = `Uptime ${h.uptime_s}s`;
        }

        if (wl.ok) {
          const items = wl.data.data || [];
          $("stat-watchlist").textContent = items.length;
          $("stat-watched").textContent = items.filter(
            (i) => i.status === "watched",
          ).length;

          const body = $("dash-watchlist-body");
          body.innerHTML = "";
          const recent = items.slice(0, 8);
          if (!recent.length) {
            body.innerHTML =
              '<tr><td colspan="4"><div class="empty"><div class="empty-icon">📋</div><div class="empty-text">No watchlist entries yet</div></div></td></tr>';
          } else {
            recent.forEach((item) => {
              body.innerHTML += `<tr>
          <td><strong>${item.movie?.title || "—"}</strong><br><span style="color:var(--muted);font-size:11px">${item.movie?.year || ""} · ${item.movie?.genre || ""}</span></td>
          <td>${statusBadge(item.status)}</td>
          <td>${stars(item.rating)}</td>
          <td style="color:var(--muted)">${fmtDate(item.created_at)}</td>
        </tr>`;
            });
          }
        }

        // movie count from metrics
        const metrics = await api("GET", "/metrics");
        if (metrics.ok && typeof metrics.data === "string") {
          const m = metrics.data.match(/movies_total (\d+)/);
          if (m) $("stat-movies").textContent = m[1];
        }
      }

      // ── MOVIES ────────────────────────────────────────────────────────────────────
      $("movie-search").oninput = () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => loadMovies(1), 400);
      };
      $("movies-prev").onclick = () => loadMovies(moviesPage - 1);
      $("movies-next").onclick = () => loadMovies(moviesPage + 1);

      async function loadMovies(page) {
        moviesPage = page;
        const q = $("movie-search").value.trim();
        const path = `/movies/?page=${page}&per_page=15${q ? `&search=${encodeURIComponent(q)}` : ""}`;
        const r = await api("GET", path);
        if (!r.ok) {
          toast("Failed to load movies", "error");
          return;
        }

        const { data: items, total, pages } = r.data;
        moviesTotal = total;
        moviesPages = pages;

        $("movies-total-info").textContent = `${total} movies`;
        $("movies-page-info").textContent = `Page ${page} of ${pages || 1}`;
        $("movies-prev").disabled = page <= 1;
        $("movies-next").disabled = page >= (pages || 1);

        const body = $("movies-body");
        body.innerHTML = "";
        if (!items.length) {
          body.innerHTML =
            '<tr><td colspan="7"><div class="empty"><div class="empty-icon">🎬</div><div class="empty-text">No movies found. Try syncing from SampleAPI!</div></div></td></tr>';
          return;
        }
        items.forEach((m) => {
          body.innerHTML += `<tr>
      <td><strong>${m.title}</strong>${m.plot ? `<br><span style="color:var(--muted);font-size:11px;display:block;max-width:220px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${m.plot}</span>` : ""}</td>
      <td>${m.year || "—"}</td>
      <td><span style="color:var(--muted)">${m.genre || "—"}</span></td>
      <td>${m.director || "—"}</td>
      <td>${m.imdb_rating ? `<span style="color:var(--accent2)">★ ${m.imdb_rating}</span>` : "—"}</td>
      <td><span style="font-size:11px;color:var(--muted)">${m.source}</span></td>
      <td>
        <div class="flex gap8">
          <button class="btn-icon" onclick="openEditMovie(${JSON.stringify(m).replace(/"/g, "&quot;")})">✏</button>
          <button class="btn-danger" onclick="deleteMovie(${m.id})">✕</button>
        </div>
      </td>
    </tr>`;
        });
      }

      // Sync
      $("sync-btn").onclick = async () => {
        $("sync-btn").textContent = "⟳ Syncing…";
        $("sync-btn").disabled = true;
        const r = await api("POST", "/movies/sync");
        $("sync-btn").textContent = "⟳ Sync from SampleAPI";
        $("sync-btn").disabled = false;
        if (r.ok) {
          toast(
            `Synced! ${r.data.data.created} created, ${r.data.data.updated} updated`,
          );
          loadMovies(1);
        } else toast(r.data.message || "Sync failed", "error");
      };

      // Add Movie Modal
      $("add-movie-btn").onclick = () => {
        editMovieId = null;
        $("movie-modal-title").textContent = "Add Movie";
        [
          "title",
          "year",
          "genre",
          "rated",
          "director",
          "actors",
          "imdb",
          "plot",
        ].forEach((f) => ($(`m-${f}`).value = ""));
        hide("movie-modal-err");
        show("movie-modal");
      };
      $("movie-modal-cancel").onclick = () => hide("movie-modal");

      function openEditMovie(m) {
        editMovieId = m.id;
        $("movie-modal-title").textContent = "Edit Movie";
        $("m-title").value = m.title || "";
        $("m-year").value = m.year || "";
        $("m-genre").value = m.genre || "";
        $("m-rated").value = m.rated || "";
        $("m-director").value = m.director || "";
        $("m-actors").value = m.actors || "";
        $("m-imdb").value = m.imdb_rating || "";
        $("m-plot").value = m.plot || "";
        hide("movie-modal-err");
        show("movie-modal");
      }

      $("movie-modal-save").onclick = async () => {
        hide("movie-modal-err");
        const body = {
          title: $("m-title").value.trim(),
          year: $("m-year").value.trim(),
          genre: $("m-genre").value.trim(),
          rated: $("m-rated").value.trim(),
          director: $("m-director").value.trim(),
          actors: $("m-actors").value.trim(),
          imdb_rating: $("m-imdb").value.trim(),
          plot: $("m-plot").value.trim(),
        };
        if (!body.title) {
          showModalErr("movie-modal-err", "Title is required");
          return;
        }
        const r = editMovieId
          ? await api("PUT", `/movies/${editMovieId}`, body)
          : await api("POST", "/movies/", body);
        if (!r.ok) {
          showModalErr("movie-modal-err", r.data.message || "Error");
          return;
        }
        hide("movie-modal");
        toast(editMovieId ? "Movie updated!" : "Movie added!");
        loadMovies(moviesPage);
      };

      async function deleteMovie(id) {
        if (!confirm("Delete this movie?")) return;
        const r = await api("DELETE", `/movies/${id}`);
        if (r.ok) {
          toast("Movie deleted");
          loadMovies(moviesPage);
        } else toast(r.data.message || "Error deleting", "error");
      }

      // ── WATCHLIST ────────────────────────────────────────────────────────────────
      $("wl-filter").onchange = loadWatchlist;

      async function loadWatchlist() {
        const status = $("wl-filter").value;
        const path = `/watchlist/${status ? `?status=${status}` : ""}`;
        const r = await api("GET", path);
        if (!r.ok) {
          toast("Failed to load watchlist", "error");
          return;
        }

        const items = r.data.data || [];
        const body = $("watchlist-body");
        body.innerHTML = "";
        if (!items.length) {
          body.innerHTML =
            '<tr><td colspan="6"><div class="empty"><div class="empty-icon">📋</div><div class="empty-text">Your watchlist is empty</div></div></td></tr>';
          return;
        }
        items.forEach((item) => {
          body.innerHTML += `<tr>
      <td><strong>${item.movie?.title || "—"}</strong><br><span style="color:var(--muted);font-size:11px">${item.movie?.year || ""} · ${item.movie?.genre || ""}</span></td>
      <td>${statusBadge(item.status)}</td>
      <td>${stars(item.rating)}</td>
      <td style="color:var(--muted);max-width:180px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${item.notes || "—"}</td>
      <td style="color:var(--muted)">${fmtDate(item.created_at)}</td>
      <td>
        <div class="flex gap8">
          <button class="btn-icon" onclick="openEditWl(${JSON.stringify(item).replace(/"/g, "&quot;")})">✏</button>
          <button class="btn-danger" onclick="deleteWl(${item.id})">✕</button>
        </div>
      </td>
    </tr>`;
        });
      }

      // Add Watchlist Modal
      $("add-wl-btn").onclick = async () => {
        // populate movie dropdown
        const r = await api("GET", "/movies/?per_page=200");
        const sel = $("wl-movie-select");
        sel.innerHTML = "";
        if (r.ok && r.data.data.length) {
          r.data.data.forEach((m) => {
            sel.innerHTML += `<option value="${m.id}">${m.title} ${m.year ? `(${m.year})` : ""}</option>`;
          });
        } else {
          sel.innerHTML = "<option disabled>No movies — sync first!</option>";
        }
        $("wl-rating").value = "";
        $("wl-notes").value = "";
        hide("wl-modal-err");
        show("wl-modal");
      };
      $("wl-modal-cancel").onclick = () => hide("wl-modal");
      $("wl-modal-save").onclick = async () => {
        hide("wl-modal-err");
        const body = {
          movie_id: parseInt($("wl-movie-select").value),
          status: $("wl-status").value,
          rating: $("wl-rating").value ? parseInt($("wl-rating").value) : null,
          notes: $("wl-notes").value.trim(),
        };
        const r = await api("POST", "/watchlist/", body);
        if (!r.ok) {
          showModalErr("wl-modal-err", r.data.message || "Error");
          return;
        }
        hide("wl-modal");
        toast("Added to watchlist!");
        loadWatchlist();
      };

      function openEditWl(item) {
        $("wl-edit-id").value = item.id;
        $("wl-edit-status").value = item.status;
        $("wl-edit-rating").value = item.rating || "";
        $("wl-edit-notes").value = item.notes || "";
        hide("wl-edit-err");
        show("wl-edit-modal");
      }
      $("wl-edit-cancel").onclick = () => hide("wl-edit-modal");
      $("wl-edit-save").onclick = async () => {
        hide("wl-edit-err");
        const id = $("wl-edit-id").value;
        const body = {
          status: $("wl-edit-status").value,
          rating: $("wl-edit-rating").value
            ? parseInt($("wl-edit-rating").value)
            : null,
          notes: $("wl-edit-notes").value.trim(),
        };
        const r = await api("PUT", `/watchlist/${id}`, body);
        if (!r.ok) {
          showModalErr("wl-edit-err", r.data.message || "Error");
          return;
        }
        hide("wl-edit-modal");
        toast("Watchlist updated!");
        loadWatchlist();
      };

      async function deleteWl(id) {
        if (!confirm("Remove from watchlist?")) return;
        const r = await api("DELETE", `/watchlist/${id}`);
        if (r.ok) {
          toast("Removed from watchlist");
          loadWatchlist();
        } else toast(r.data.message || "Error", "error");
      }

      // ── HEALTH ────────────────────────────────────────────────────────────────────
      async function loadHealth() {
        const [hRes, alertRes, metRes] = await Promise.all([
          api("GET", "/health"),
          api("GET", "/alerts"),
          api("GET", "/metrics"),
        ]);

        // Status card
        if (hRes.ok) {
          const h = hRes.data;
          const ok = h.status === "healthy";
          $("health-status-display").innerHTML = `
      <div class="health-status ${ok ? "health-ok" : "health-bad"}" style="margin-bottom:12px">
        <span class="dot ${ok ? "pulse" : ""}"></span> ${h.status.toUpperCase()}
      </div>
      <div style="font-size:13px;color:var(--muted);line-height:2">
        Database: <strong style="color:${h.checks.database === "ok" ? "var(--success)" : "var(--accent)"}">${h.checks.database}</strong><br>
        Uptime: <strong>${h.uptime_s}s</strong><br>
        Version: <strong>${h.version}</strong>
      </div>
    `;
          $("health-badge").className =
            `health-status ${ok ? "health-ok" : "health-bad"}`;
          $("health-badge").innerHTML =
            `<span class="dot ${ok ? "pulse" : ""}"></span> ${ok ? "Healthy" : "Degraded"}`;
        }

        // Metrics
        if (metRes.ok && typeof metRes.data === "string") {
          const lines = metRes.data
            .split("\n")
            .filter((l) => !l.startsWith("#"));
          $("health-metrics").innerHTML =
            `<div style="font-family:var(--font-mono);font-size:12px;line-height:2.2;color:var(--muted)">` +
            lines
              .map((l) => {
                const [k, v] = l.split(" ");
                return `<div>${k.replace(/_/g, " ")}: <strong style="color:var(--text)">${v}</strong></div>`;
              })
              .join("") +
            "</div>";
        }

        // Alerts log
        if (alertRes.ok) {
          const alerts = alertRes.data.alerts || [];
          const log = $("alerts-log");
          if (!alerts.length) {
            log.innerHTML = '<span class="log-ok">✓ No recent alerts</span>';
          } else {
            log.innerHTML = alerts
              .reverse()
              .map((a) => {
                const ts = new Date(a.ts * 1000).toISOString();
                if (a.type === "high_error_rate") {
                  return `<div class="log-err">[${ts}] [ALERT] HIGH_ERROR_RATE endpoint=${a.endpoint} count=${a.count}</div>`;
                }
                return `<div class="log-warn">[${ts}] [ALERT] SLOW_RESPONSE endpoint=${a.endpoint} ms=${a.response_time_ms}</div>`;
              })
              .join("");
          }
        }
      }

      // ── HELPERS ───────────────────────────────────────────────────────────────────
      function showModalErr(elId, msg) {
        const el = $(elId);
        el.textContent = msg;
        show(elId);
      }

      // Close modals on overlay click
      ["movie-modal", "wl-modal", "wl-edit-modal"].forEach((id) => {
        $(id).addEventListener("click", (e) => {
          if (e.target === $(id)) hide(id);
        });
      });

      restoreAuthState();
