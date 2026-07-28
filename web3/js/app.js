(function() {
    'use strict';

    // ═══════════════════════════════════════════════════════
    //  DATOS — colores, horas, provincias, municipios
    // ═══════════════════════════════════════════════════════

    var COLORES = [
        { nombre: 'azul',     hex: '#1976d2' },
        { nombre: 'negro',    hex: '#212121' },
        { nombre: 'gris',     hex: '#757575' },
        { nombre: 'verde',    hex: '#388e3c' },
        { nombre: 'marr\u00f3n', hex: '#5d4037' },
        { nombre: 'amarillo', hex: '#fbc02d' },
        { nombre: 'rojo',     hex: '#d32f2f' },
        { nombre: 'rosa',     hex: '#e91e63' },
        { nombre: 'violeta',  hex: '#7b1fa2' }
    ];
    var coloresSeleccionados = [];

    var HORAS = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23];
    var horasSeleccionadas = [];
    var horaActual = 12;   // última hora clickeada → maneja la paleta

    var PROVINCIAS = [
        { nombre: 'CABA' },
        { nombre: 'Buenos Aires' },
        { nombre: 'C\u00f3rdoba' }
    ];
    var provinciasSeleccionadas = [];

    var MUNICIPIOS = [
        'Luj\u00e1n', 'Bell Ville', 'C\u00f3rdoba', 'Rojas',
        'Villa Mar\u00eda', 'Oncativo', 'Carmen de Areco',
        'Ballesteros', 'Salto', 'Saladillo'
    ];
    var municipiosSeleccionados = [];

    // ═══════════════════════════════════════════════════════
    //  FLOW — duración y ciclo de paleta
    // ═══════════════════════════════════════════════════════

    var FLOW = {
        activo: false,
        inicio: 0,
        duracionMs: 300000,  // 5 minutos
        horas: [],           // horas que recorre (copia al iniciar)
        ultimoSegundo: -1    // para refrescar botón cada 1s
    };

    // ═══════════════════════════════════════════════════════
    //  BLOQUES — definición y estado
    // ═══════════════════════════════════════════════════════

    var BLOQUES = [
        { id: 'colores',     tipo: 'selector', titulo: 'Colores',     w: 900, h: 100, mx: 0, my: 0 },
        { id: 'horas',       tipo: 'selector', titulo: 'Horas',       w: 900, h: 120, mx: 0, my: 0 },
        { id: 'provincias',  tipo: 'selector', titulo: 'Provincias',  w: 700, h: 80,  mx: 0, my: 0 },
        { id: 'municipios',  tipo: 'selector', titulo: 'Municipios',  w: 800, h: 80,  mx: 0, my: 0 },
        { id: 'tags',        tipo: 'selector', titulo: 'Tags',        w: 600, h: 320, mx: 0, my: 0 },
        { id: 'imagenes',    tipo: 'media',    titulo: 'Im\u00e1genes', w: 620, h: 400, mx: 0, my: 0 },
        { id: 'videos',      tipo: 'media',    titulo: 'Videos',      w: 540, h: 360, mx: 0, my: 0 },
        { id: 'textos',      tipo: 'media',    titulo: 'Textos',      w: 440, h: 280, mx: 0, my: 0 },
        { id: 'sonidos',     tipo: 'media',    titulo: 'Sonidos',     w: 340, h: 200, mx: 0, my: 0 },
        { id: 'mapa',        tipo: 'media',    titulo: 'Mapa',        w: 540, h: 360, mx: 0, my: 0 }
    ];

    // ═══════════════════════════════════════════════════════
    //  PALETAS POR HORA — 24 momentos del día
    // ═══════════════════════════════════════════════════════

    var PALETTAS = [
        { bg:[8,8,18],      text:[110,120,140], accent:[50,60,90],    surface:[14,14,28],   slider:[40,50,80]  },
        { bg:[6,6,16],      text:[100,110,135], accent:[45,55,85],    surface:[12,12,26],   slider:[35,45,75]  },
        { bg:[5,5,15],      text:[95,105,130],  accent:[40,50,80],    surface:[11,11,24],   slider:[30,40,70]  },
        { bg:[5,5,15],      text:[90,100,125],  accent:[38,48,78],    surface:[10,10,22],   slider:[28,38,68]  },
        { bg:[12,10,22],    text:[100,100,120], accent:[60,50,80],    surface:[18,16,30],   slider:[50,42,70]  },
        { bg:[40,25,50],    text:[180,150,170], accent:[220,140,120], surface:[55,38,65],   slider:[180,100,90] },
        { bg:[80,45,55],    text:[240,200,190], accent:[255,160,100], surface:[100,60,70],  slider:[240,140,90] },
        { bg:[180,120,80],  text:[60,30,10],    accent:[255,180,80],  surface:[200,140,100],slider:[255,160,60] },
        { bg:[220,200,170], text:[60,50,30],    accent:[200,150,60],  surface:[235,220,195],slider:[220,160,60] },
        { bg:[230,225,210], text:[55,50,35],    accent:[180,140,60],  surface:[240,236,225],slider:[200,160,70] },
        { bg:[220,228,235], text:[40,55,70],    accent:[80,130,180],  surface:[235,240,248],slider:[80,130,180] },
        { bg:[228,238,245], text:[35,55,75],    accent:[70,140,200],  surface:[240,248,255],slider:[70,140,200] },
        { bg:[232,240,248], text:[30,55,78],    accent:[60,130,195],  surface:[242,250,255],slider:[60,130,195] },
        { bg:[235,228,215], text:[65,55,35],    accent:[200,150,60],  surface:[245,240,228],slider:[200,150,60] },
        { bg:[230,215,185], text:[75,55,25],    accent:[210,140,50],  surface:[240,228,205],slider:[210,140,50] },
        { bg:[225,200,160], text:[80,50,20],    accent:[220,130,40],  surface:[238,218,185],slider:[220,130,40] },
        { bg:[215,175,120], text:[70,40,10],    accent:[240,120,30],  surface:[230,195,150],slider:[240,120,30] },
        { bg:[200,130,70],  text:[60,25,5],     accent:[255,120,40],  surface:[220,155,100],slider:[255,120,40] },
        { bg:[160,80,55],   text:[240,180,160], accent:[255,100,50],  surface:[180,100,75], slider:[255,100,50] },
        { bg:[90,50,65],    text:[200,170,190], accent:[180,100,140], surface:[110,65,80],  slider:[160,90,120] },
        { bg:[35,25,48],    text:[140,130,160], accent:[100,80,130],  surface:[48,38,62],   slider:[90,70,120] },
        { bg:[18,18,32],    text:[120,120,150], accent:[70,70,110],   surface:[26,26,42],   slider:[60,60,100] },
        { bg:[12,12,25],    text:[110,115,140], accent:[55,60,95],    surface:[20,20,35],   slider:[48,52,85]  },
        { bg:[10,10,22],    text:[105,110,135], accent:[50,58,90],    surface:[16,16,30],   slider:[42,48,80]  }
    ];
    var NOMBRES_HORA = [
        'Madrugada','Madrugada','Madrugada','Madrugada',
        'Amanecer','Amanecer','Amanecer','Sol naciente',
        'Ma\u00f1ana','Ma\u00f1ana','Media ma\u00f1ana','Mediod\u00eda',
        'Mediod\u00eda','Tarde temprana','Tarde','Tarde',
        'Tarde tard\u00eda','Atardecer','Atardecer','Crep\u00fasculo',
        'Noche temprana','Noche','Noche','Noche'
    ];

    // ═══════════════════════════════════════════════════════
    //  INTERPOLACIÓN
    // ═══════════════════════════════════════════════════════

    function lerp(a, b, t) { return a + (b - a) * t; }
    function lerpColor(c1, c2, t) {
        return [
            Math.round(lerp(c1[0], c2[0], t)),
            Math.round(lerp(c1[1], c2[1], t)),
            Math.round(lerp(c1[2], c2[2], t))
        ];
    }
    function rgb(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }
    function interpolar(hora) {
        var h = ((hora % 24) + 24) % 24;
        var i0 = Math.floor(h);
        var i1 = (i0 + 1) % 24;
        var t = h - i0;
        var p0 = PALETTAS[i0];
        var p1 = PALETTAS[i1];
        return {
            bg:      lerpColor(p0.bg, p1.bg, t),
            text:    lerpColor(p0.text, p1.text, t),
            accent:  lerpColor(p0.accent, p1.accent, t),
            surface: lerpColor(p0.surface, p1.surface, t),
            slider:  lerpColor(p0.slider, p1.slider, t)
        };
    }

    // ═══════════════════════════════════════════════════════
    //  CANVAS + CÁMARA
    // ═══════════════════════════════════════════════════════

    var canvas = document.getElementById('lienzo');
    var ctx = canvas.getContext('2d');
    var dims = { w: 0, h: 0 };
    var cam = { tx: 0, ty: 0, scale: 1, zoomMin: 0.001, zoomMax: 5 };
    var drag = { active: false, lx: 0, ly: 0, ltx: 0, lty: 0 };

    var zoomSlider = document.getElementById('zoom-slider');
    var zoomLabel  = document.getElementById('zoom-label');
    var zoomInBtn  = document.getElementById('zoom-in');
    var zoomOutBtn = document.getElementById('zoom-out');

    var paleta = interpolar(12);
    var paletaTarget = paleta;
    var TASA = 0.08;

    // ═══════════════════════════════════════════════════════
    //  ALGORITMO DE COLOCACIÓN ALEATORIA
    // ═══════════════════════════════════════════════════════

    function shuffle(arr) {
        for (var i = arr.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
        }
        return arr;
    }

    function haySuperposicion(b, excluir) {
        for (var i = 0; i < BLOQUES.length; i++) {
            var o = BLOQUES[i];
            if (o === b || o === excluir) continue;
            if (o.mx === 0 && o.my === 0) continue; // no colocado aún
            if (b.mx < o.mx + o.w + 1 && b.mx + b.w + 1 > o.mx &&
                b.my < o.my + o.h + 1 && b.my + b.h + 1 > o.my) {
                return true;
            }
        }
        return false;
    }

    function colocarBloques() {
        // --- MEDIA TERRITORY (contiguo) ---
        var mediaIds = ['imagenes', 'videos', 'textos', 'sonidos', 'mapa'];
        shuffle(mediaIds);
        var colocados = [];

        // Primer bloque en posición aleatoria centrada
        var primero = BLOQUES.filter(function(b){return b.id===mediaIds[0];})[0];
        primero.mx = Math.round(Math.random() * 500 - 250);
        primero.my = Math.round(Math.random() * 500 - 250);
        colocados.push(primero);

        for (var mi = 1; mi < mediaIds.length; mi++) {
            var b = BLOQUES.filter(function(x){return x.id===mediaIds[mi];})[0];
            var exito = false;
            for (var intento = 0; intento < 80; intento++) {
                var ref = colocados[Math.floor(Math.random() * colocados.length)];
                var edge = Math.floor(Math.random() * 4);
                var bx, by;

                // offset aleatorio a lo largo del borde
                var offX = Math.round((Math.random() - 0.5) * Math.max(ref.w - b.w, 30));
                var offY = Math.round((Math.random() - 0.5) * Math.max(ref.h - b.h, 30));

                // clamp para que no quede colgando
                var minOffX = -b.w + 20;
                var maxOffX = ref.w - 20;
                var minOffY = -b.h + 20;
                var maxOffY = ref.h - 20;
                offX = Math.max(minOffX, Math.min(maxOffX, offX));
                offY = Math.max(minOffY, Math.min(maxOffY, offY));

                switch (edge) {
                    case 0: // derecha
                        bx = ref.mx + ref.w;
                        by = ref.my + offY;
                        break;
                    case 1: // abajo
                        bx = ref.mx + offX;
                        by = ref.my + ref.h;
                        break;
                    case 2: // izquierda
                        bx = ref.mx - b.w;
                        by = ref.my + offY;
                        break;
                    case 3: // arriba
                        bx = ref.mx + offX;
                        by = ref.my - b.h;
                        break;
                }

                b.mx = bx;
                b.my = by;
                if (!haySuperposicion(b, ref)) {
                    colocados.push(b);
                    exito = true;
                    break;
                }
            }
            if (!exito) {
                // Fallback: a la derecha de todos
                var maxX = -Infinity;
                colocados.forEach(function(c) {
                    if (c.mx + c.w > maxX) maxX = c.mx + c.w;
                });
                b.mx = maxX + 30;
                b.my = colocados[0].my + Math.round((Math.random() - 0.5) * 120);
                colocados.push(b);
            }
        }

        // --- SELECTORES (no se superponen con nada) ---
        var selIds = ['colores', 'horas', 'provincias', 'municipios', 'tags'];
        shuffle(selIds);
        var area = { x: -900, y: -900, w: 1800, h: 1800 };

        selIds.forEach(function(id) {
            var b = BLOQUES.filter(function(x){return x.id===id;})[0];
            for (var intento = 0; intento < 120; intento++) {
                b.mx = Math.round(area.x + Math.random() * (area.w - b.w));
                b.my = Math.round(area.y + Math.random() * (area.h - b.h));
                if (!haySuperposicion(b)) break;
            }
        });
    }

    // ═══════════════════════════════════════════════════════
    //  SINCRO BLOQUES → HTML
    // ═══════════════════════════════════════════════════════

    function syncBlocks() {
        var mundo = document.getElementById('mundo');
        // Crear elementos de bloque que falten
        BLOQUES.forEach(function(b) {
            var el = document.getElementById('bloque-' + b.id);
            if (!el) {
                el = document.createElement('div');
                el.id = 'bloque-' + b.id;
                el.className = 'bloque' + (b.tipo === 'media' ? ' bloque-media' : '');
                el.innerHTML = '<div class="bloque-titulo">' + b.titulo + '</div>'
                            + '<div class="bloque-contenido"></div>';
                mundo.appendChild(el);
                // Render contenido según tipo
                renderContenidoBloque(b.id, el.querySelector('.bloque-contenido'));
            }
            // Posición y escala
            var sx = Math.round(b.mx * cam.scale + cam.tx);
            var sy = Math.round(b.my * cam.scale + cam.ty);
            el.style.transform = 'translate(' + sx + 'px, ' + sy + 'px) scale(' + cam.scale + ')';
            el.style.width  = b.w + 'px';
            el.style.height = b.h + 'px';
            el.style.display = 'block';
        });
    }

    function renderContenidoBloque(id, cont) {
        switch (id) {
            case 'colores':   renderChipsColores(cont); break;
            case 'horas':     renderChipsHoras(cont); break;
            case 'provincias': renderChipsProvincias(cont); break;
            case 'municipios': renderChipsMunicipios(cont); break;
            case 'tags':      renderTags(cont); break;
            default:
                cont.innerHTML = '<div class="media-placeholder">' + iconoMedia(id) + '</div>';
        }
    }

    function iconoMedia(id) {
        var map = {
            imagenes: '\uD83D\uDCF7',
            videos: '\uD83C\uDFAC',
            textos: '\uD83D\uDCDD',
            sonidos: '\uD83C\uDFB5',
            mapa: '\uD83D\uDDFA\uFE0F'
        };
        return map[id] || '\u2753';
    }

    // ═══════════════════════════════════════════════════════
    //  CHIPS: COLORES
    // ═══════════════════════════════════════════════════════

    function renderChipsColores(cont) {
        cont.classList.add('columnas');
        cont.style.columnCount = '3';
        var html = '';
        COLORES.forEach(function(c) {
            var activo = coloresSeleccionados.indexOf(c.nombre) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-color" data-valor="' + c.nombre + '">'
                  + '<span class="chip-bola" style="background:' + c.hex + '"></span>'
                  + c.nombre
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-colores">Todos</span>';
        cont.innerHTML = html;
        // Bind events
        cont.querySelectorAll('[data-accion="toggle-color"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                toggleColor(this.dataset.valor);
            });
        });
        actualizarInfoColores();
    }

    function toggleColor(nombre) {
        var idx = coloresSeleccionados.indexOf(nombre);
        if (idx === -1) coloresSeleccionados.push(nombre);
        else coloresSeleccionados.splice(idx, 1);
        // Actualizar chips visualmente
        document.querySelectorAll('#bloque-colores [data-accion="toggle-color"]').forEach(function(btn) {
            if (btn.dataset.valor === nombre) btn.classList.toggle('activo');
        });
        actualizarInfoColores();
    }

    function actualizarInfoColores() {
        var info = document.getElementById('info-colores');
        if (!info) return;
        if (coloresSeleccionados.length === 0) info.textContent = 'Todos';
        else if (coloresSeleccionados.length === 1) info.textContent = coloresSeleccionados[0];
        else info.textContent = coloresSeleccionados.length + ' colores';
    }

    // ═══════════════════════════════════════════════════════
    //  CHIPS: HORAS
    // ═══════════════════════════════════════════════════════

    function renderChipsHoras(cont) {
        cont.classList.add('columnas');
        cont.style.columnCount = '6';
        var html = '';
        HORAS.forEach(function(h) {
            var hh = (h < 10 ? '0' : '') + h;
            var activo = horasSeleccionadas.indexOf(h) !== -1 ? ' activo' : '';
            html += '<button class="chip-hora' + activo + '" data-accion="toggle-hora" data-valor="' + h + '">'
                  + hh
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-horas">Ninguna</span>';
        cont.innerHTML = html;
        cont.querySelectorAll('[data-accion="toggle-hora"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                toggleHora(parseInt(this.dataset.valor));
            });
        });
        actualizarInfoHoras();
    }

    function toggleHora(h) {
        if (FLOW.activo) return; // bloqueado durante el flujo
        var idx = horasSeleccionadas.indexOf(h);
        if (idx === -1) {
            horasSeleccionadas.push(h);
        } else {
            horasSeleccionadas.splice(idx, 1);
        }
        // La paleta sigue la última hora clickeada
        horaActual = h;

        document.querySelectorAll('#bloque-horas [data-accion="toggle-hora"]').forEach(function(btn) {
            if (parseInt(btn.dataset.valor) === h) btn.classList.toggle('activo');
        });
        actualizarInfoHoras();
        // Transicionar paleta
        paletaTarget = interpolar(horaActual);
    }

    function actualizarInfoHoras() {
        var info = document.getElementById('info-horas');
        if (!info) return;
        if (horasSeleccionadas.length === 0) info.textContent = 'Ninguna';
        else {
            var txt = horasSeleccionadas.slice(0, 3).map(function(h) {
                return (h < 10 ? '0' : '') + h + ':00';
            }).join(' ');
            if (horasSeleccionadas.length > 3) txt += ' +' + (horasSeleccionadas.length - 3);
            info.textContent = txt;
        }
    }

    // ═══════════════════════════════════════════════════════
    //  CHIPS: PROVINCIAS
    // ═══════════════════════════════════════════════════════

    function renderChipsProvincias(cont) {
        cont.classList.add('columnas');
        cont.style.columnCount = '3';
        var html = '';
        PROVINCIAS.forEach(function(p) {
            var activo = provinciasSeleccionadas.indexOf(p.nombre) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-provincia" data-valor="' + p.nombre + '">'
                  + p.nombre
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-provincias">Todas</span>';
        cont.innerHTML = html;
        cont.querySelectorAll('[data-accion="toggle-provincia"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                toggleProvincia(this.dataset.valor);
            });
        });
        actualizarInfoProvincias();
    }

    function toggleProvincia(nombre) {
        var idx = provinciasSeleccionadas.indexOf(nombre);
        if (idx === -1) provinciasSeleccionadas.push(nombre);
        else provinciasSeleccionadas.splice(idx, 1);
        document.querySelectorAll('#bloque-provincias [data-accion="toggle-provincia"]').forEach(function(btn) {
            if (btn.dataset.valor === nombre) btn.classList.toggle('activo');
        });
        actualizarInfoProvincias();
    }

    function actualizarInfoProvincias() {
        var info = document.getElementById('info-provincias');
        if (!info) return;
        if (provinciasSeleccionadas.length === 0) info.textContent = 'Todas';
        else if (provinciasSeleccionadas.length === 1) info.textContent = provinciasSeleccionadas[0];
        else info.textContent = provinciasSeleccionadas.length + ' provincias';
    }

    // ═══════════════════════════════════════════════════════
    //  CHIPS: MUNICIPIOS
    // ═══════════════════════════════════════════════════════

    function renderChipsMunicipios(cont) {
        cont.classList.add('columnas');
        cont.style.columnCount = '2';
        var html = '';
        MUNICIPIOS.forEach(function(m) {
            var activo = municipiosSeleccionados.indexOf(m) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-municipio" data-valor="' + m + '">'
                  + m
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-municipios">Todos</span>';
        cont.innerHTML = html;
        cont.querySelectorAll('[data-accion="toggle-municipio"]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                toggleMunicipio(this.dataset.valor);
            });
        });
        actualizarInfoMunicipios();
    }

    function toggleMunicipio(nombre) {
        var idx = municipiosSeleccionados.indexOf(nombre);
        if (idx === -1) municipiosSeleccionados.push(nombre);
        else municipiosSeleccionados.splice(idx, 1);
        document.querySelectorAll('#bloque-municipios [data-accion="toggle-municipio"]').forEach(function(btn) {
            if (btn.dataset.valor === nombre) btn.classList.toggle('activo');
        });
        actualizarInfoMunicipios();
    }

    function actualizarInfoMunicipios() {
        var info = document.getElementById('info-municipios');
        if (!info) return;
        if (municipiosSeleccionados.length === 0) info.textContent = 'Todos';
        else if (municipiosSeleccionados.length === 1) info.textContent = municipiosSeleccionados[0];
        else info.textContent = municipiosSeleccionados.length + ' municipios';
    }

    // ═══════════════════════════════════════════════════════
    //  TAGS (placeholder)
    // ═══════════════════════════════════════════════════════

    var TAGS_PLACEHOLDER = [
        'ruta', 'bicicleta', 'atardecer', 'asfalto',
        'arboles', 'nubes', 'sol', 'paisaje',
        'pedaleo', 'polvo', 'camino', 'horizonte',
        'descanso', 'almuerzo', 'sombra', 'calor',
        'viento', 'llanura', 'sierras', 'rio'
    ];

    function renderTags(cont) {
        var html = '<div class="tag-cloud">';
        var shuffled = shuffle(TAGS_PLACEHOLDER.slice());
        shuffled.forEach(function(tag, i) {
            var size = 0.55 + Math.random() * 0.4;
            html += '<span class="tag-item" style="font-size:' + size.toFixed(2) + 'rem">'
                  + tag
                  + '</span>';
        });
        html += '</div>';
        cont.innerHTML = html;
    }

    // ═══════════════════════════════════════════════════════
    //  FLOW — iniciar, actualizar, detener
    // ═══════════════════════════════════════════════════════

    function iniciarFlow() {
        // Congelar las horas seleccionadas como el ciclo
        FLOW.horas = horasSeleccionadas.slice();
        if (FLOW.horas.length < 2) {
            // Si hay menos de 2 horas seleccionadas, usar todas
            FLOW.horas = HORAS.slice();
        }
        FLOW.inicio = Date.now();
        FLOW.activo = true;
        FLOW.ultimoSegundo = -1;
        document.getElementById('btn-fluir').classList.add('activo');
        actualizarBotonFluir();
    }

    function detenerFlow() {
        FLOW.activo = false;
        document.getElementById('btn-fluir').classList.remove('activo');
        document.getElementById('btn-fluir').textContent = 'Fluir';
        // Dejar la paleta donde está
    }

    function actualizarFlow() {
        var elapsed = Date.now() - FLOW.inicio;
        if (elapsed >= FLOW.duracionMs) {
            detenerFlow();
            return;
        }

        var horas = FLOW.horas;
        var progreso = elapsed / FLOW.duracionMs;            // 0..1
        var pos = progreso * horas.length;                   // 0..N
        var idx = Math.floor(pos) % horas.length;
        var t = pos - Math.floor(pos);

        var h1 = horas[idx];
        var h2 = horas[(idx + 1) % horas.length];

        // Diferencia con wrapping (ej: 22 → 02 debe ir por 23,0,1)
        var diff = h2 - h1;
        if (diff > 12) diff -= 24;
        if (diff < -12) diff += 24;
        var interpHour = h1 + diff * t;
        if (interpHour < 0) interpHour += 24;
        if (interpHour >= 24) interpHour -= 24;

        paletaTarget = interpolar(interpHour);

        // Actualizar botón cada ~1 segundo
        var seg = Math.floor(elapsed / 1000);
        if (seg !== FLOW.ultimoSegundo) {
            FLOW.ultimoSegundo = seg;
            actualizarBotonFluir();
        }
    }

    function actualizarBotonFluir() {
        var btn = document.getElementById('btn-fluir');
        if (!btn) return;
        if (!FLOW.activo) {
            btn.textContent = 'Fluir';
            return;
        }
        var restante = Math.max(0, FLOW.duracionMs - (Date.now() - FLOW.inicio));
        var mins = Math.floor(restante / 60000);
        var segs = Math.floor((restante % 60000) / 1000);
        btn.textContent = (mins < 10 ? '0' : '') + mins + ':'
                        + (segs < 10 ? '0' : '') + segs;
    }

    // ═══════════════════════════════════════════════════════
    //  GRID + DIBUJAR
    // ═══════════════════════════════════════════════════════

    function drawGrid() {
        var vw = dims.w / cam.scale;
        var vh = dims.h / cam.scale;
        var spacing = Math.round(Math.max(dims.w, dims.h) / 10);

        var worldLeft   = -cam.tx / cam.scale;
        var worldTop    = -cam.ty / cam.scale;
        var worldRight  = worldLeft + vw;
        var worldBottom = worldTop + vh;

        ctx.strokeStyle = rgb(paleta.accent);
        ctx.globalAlpha = 0.1;
        ctx.lineWidth = 1;
        ctx.beginPath();

        var startX = Math.floor(worldLeft / spacing) * spacing;
        for (var x = startX; x <= worldRight; x += spacing) {
            var sx = Math.round(x * cam.scale + cam.tx) + 0.5;
            ctx.moveTo(sx, 0);
            ctx.lineTo(sx, dims.h);
        }
        var startY = Math.floor(worldTop / spacing) * spacing;
        for (var y = startY; y <= worldBottom; y += spacing) {
            var sy = Math.round(y * cam.scale + cam.ty) + 0.5;
            ctx.moveTo(0, sy);
            ctx.lineTo(dims.w, sy);
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    function dibujar() {
        ctx.clearRect(0, 0, dims.w, dims.h);
        ctx.fillStyle = rgb(paleta.bg);
        ctx.fillRect(0, 0, dims.w, dims.h);
        drawGrid();
        syncBlocks();
    }

    // ═══════════════════════════════════════════════════════
    //  TICK — transición suave de paleta (cada 16ms)
    // ═══════════════════════════════════════════════════════

    function tick() {
        // 1. Si el flow está activo, actualizar la paleta target
        if (FLOW.activo) {
            actualizarFlow();
        }

        // 2. Interpolación suave hacia el target
        var cambio = false;
        ['bg','text','accent','surface','slider'].forEach(function(k) {
            var a = paleta[k];
            var b = paletaTarget[k];
            if (a[0] !== b[0] || a[1] !== b[1] || a[2] !== b[2]) {
                paleta[k] = lerpColor(a, b, TASA);
                cambio = true;
            }
        });
        if (cambio) {
            dibujar();
            actualizarCSS();
        }
    }
    setInterval(tick, 16);

    // ═══════════════════════════════════════════════════════
    //  CSS vars + zoom controls
    // ═══════════════════════════════════════════════════════

    function actualizarCSS() {
        document.documentElement.style.setProperty('--thumb', rgb(paleta.accent));
        document.documentElement.style.setProperty('--text', rgb(paleta.text));
        document.documentElement.style.setProperty('--marcas', rgb(paleta.text));
        zoomInBtn.style.background = rgb(paleta.surface);
        zoomInBtn.style.color = rgb(paleta.text);
        zoomOutBtn.style.background = rgb(paleta.surface);
        zoomOutBtn.style.color = rgb(paleta.text);
        zoomLabel.style.color = rgb(paleta.text);
    }

    // ═══════════════════════════════════════════════════════
    //  RESIZE
    // ═══════════════════════════════════════════════════════

    function redimensionar() {
        dims.w = window.innerWidth;
        dims.h = window.innerHeight;
        canvas.width = dims.w;
        canvas.height = dims.h;
        ajustarCamaraABloques();
        dibujar();
    }
    window.addEventListener('resize', redimensionar);

    // ═══════════════════════════════════════════════════════
    //  ZOOM + PAN
    // ═══════════════════════════════════════════════════════

    function actualizarZoomUI() {
        zoomSlider.min = cam.zoomMin;
        zoomSlider.max = cam.zoomMax;
        zoomSlider.value = cam.scale;
        zoomLabel.textContent = cam.scale.toFixed(1) + '\u00d7';
    }

    canvas.addEventListener('wheel', function(e) {
        e.preventDefault();
        var step = 0.06;
        cam.scale *= e.deltaY > 0 ? (1 - step) : (1 + step);
        cam.scale = Math.max(cam.zoomMin, Math.min(cam.zoomMax, cam.scale));
        actualizarZoomUI();
        dibujar();
    }, { passive: false });

    zoomSlider.addEventListener('input', function() {
        cam.scale = parseFloat(this.value);
        actualizarZoomUI();
        dibujar();
    });

    zoomInBtn.addEventListener('click', function() {
        cam.scale = Math.min(cam.zoomMax, cam.scale * 1.3);
        actualizarZoomUI();
        dibujar();
    });
    zoomOutBtn.addEventListener('click', function() {
        cam.scale = Math.max(cam.zoomMin, cam.scale / 1.3);
        actualizarZoomUI();
        dibujar();
    });

    canvas.addEventListener('mousedown', function(e) {
        drag.active = true;
        drag.lx = e.clientX;
        drag.ly = e.clientY;
        drag.ltx = cam.tx;
        drag.lty = cam.ty;
    });
    window.addEventListener('mousemove', function(e) {
        if (!drag.active) return;
        cam.tx = drag.ltx + (e.clientX - drag.lx);
        cam.ty = drag.lty + (e.clientY - drag.ly);
        dibujar();
    });
    window.addEventListener('mouseup', function() { drag.active = false; });

    canvas.addEventListener('dblclick', function() {
        ajustarCamaraABloques();
        dibujar();
    });

    // ═══════════════════════════════════════════════════════
    //  AJUSTAR CÁMARA A TODOS LOS BLOQUES
    // ═══════════════════════════════════════════════════════

    function ajustarCamaraABloques() {
        var minX = Infinity, maxX = -Infinity;
        var minY = Infinity, maxY = -Infinity;
        BLOQUES.forEach(function(b) {
            if (b.mx < minX) minX = b.mx;
            if (b.mx + b.w > maxX) maxX = b.mx + b.w;
            if (b.my < minY) minY = b.my;
            if (b.my + b.h > maxY) maxY = b.my + b.h;
        });
        if (!isFinite(minX)) return;
        var cx = (minX + maxX) / 2;
        var cy = (minY + maxY) / 2;
        var rangeX = maxX - minX || 500;
        var rangeY = maxY - minY || 500;
        var padding = 1.05;
        var sX = dims.w / (rangeX * padding);
        var sY = dims.h / (rangeY * padding);
        cam.zoomMin = Math.min(sX, sY);
        cam.zoomMax = 5;
        cam.scale = Math.max(cam.zoomMin, Math.min(cam.zoomMax, cam.scale));
        cam.tx = dims.w / 2 - cx * cam.scale;
        cam.ty = dims.h / 2 - cy * cam.scale;
        actualizarZoomUI();
    }

    // ═══════════════════════════════════════════════════════
    //  ARRANQUE
    //  ⚠ ORDEN: primero dims, después cámara, después dibujar
    // ═══════════════════════════════════════════════════════

    colocarBloques();
    dims.w = window.innerWidth;
    dims.h = window.innerHeight;
    canvas.width = dims.w;
    canvas.height = dims.h;
    ajustarCamaraABloques();
    dibujar();
    actualizarCSS();
    actualizarZoomUI();

    // Botón fluir
    document.getElementById('btn-fluir').addEventListener('click', function() {
        if (FLOW.activo) {
            detenerFlow();
            this.textContent = 'Fluir';
            this.classList.remove('activo');
        } else {
            iniciarFlow();
        }
    });

})();
