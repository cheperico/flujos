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

    var DATOS_CARGADOS = false;
    var DATOS_TOTAL = 0;
    var DATOS_API = null;
    var TAGS_API = null;
    var MEDIOS_FILTRADOS = null;
    var MENSAJES_TELEGRAM = null;
    var MENSAJES_TELEGRAM_MUNICIPIO = '';

    var SLIDESHOW = {
        items: [],
        index: 0,
        cont: null,
        ultimoAvance: 0,
        intervaloMs: 4000  // 4 segundos entre imágenes
    };

    var VENTANA_CHAT = {
        tamano: 10,
        inicio: 0,
        ultimoInicio: -1
    };

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

    var BLOQUES = [];
    var BLOQUES_TEMPLATE = [
        { id: 'colores',     tipo: 'selector', titulo: 'Colores',     w: 500, h: 220 },
        { id: 'horas',       tipo: 'selector', titulo: 'Horas',       w: 550, h: 260 },
        { id: 'provincias',  tipo: 'selector', titulo: 'Provincias',  w: 350, h: 160 },
        { id: 'municipios',  tipo: 'selector', titulo: 'Municipios',  w: 420, h: 340 },
        { id: 'tags',        tipo: 'selector', titulo: 'Tags',        w: 500, h: 380 },
        { id: 'imagenes',    tipo: 'media',    titulo: 'Im\u00e1genes', w: 700, h: 520 },
        { id: 'videos',      tipo: 'media',    titulo: 'Videos',      w: 520, h: 380 },
        { id: 'textos',      tipo: 'media',    titulo: 'Textos',      w: 420, h: 300 },
        { id: 'sonidos',     tipo: 'media',    titulo: 'Sonidos',     w: 340, h: 240 },
        { id: 'mapa',        tipo: 'media',    titulo: 'Mapa',        w: 520, h: 380 },
        { id: 'comunicacion', tipo: 'media',   titulo: 'Comunicaci\u00f3n', w: 480, h: 420 }
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
    //  MUNDO FINITO — límites que contienen todos los bloques
    // ═══════════════════════════════════════════════════════

    var worldBounds = { x: 0, y: 0, w: 0, h: 0 };

    function calcularBounds() {
        var minX = Infinity, maxX = -Infinity;
        var minY = Infinity, maxY = -Infinity;
        BLOQUES.forEach(function(b) {
            if (b.mx < minX) minX = b.mx;
            if (b.mx + b.w > maxX) maxX = b.mx + b.w;
            if (b.my < minY) minY = b.my;
            if (b.my + b.h > maxY) maxY = b.my + b.h;
        });
        if (!isFinite(minX)) return;
        var pad = 40;
        worldBounds.x = minX - pad;
        worldBounds.y = minY - pad;
        worldBounds.w = (maxX - minX) + pad * 2;
        worldBounds.h = (maxY - minY) + pad * 2;
    }

    function ajustarProporcionMundo() {
        if (worldBounds.w === 0 || dims.w === 0) return;
        var ratioPantalla = dims.w / dims.h;
        var ratioMundo = worldBounds.w / worldBounds.h;
        if (ratioMundo > ratioPantalla) {
            // Mundo más ancho que la pantalla → aumentar altura
            var nuevoH = worldBounds.w / ratioPantalla;
            var diff = nuevoH - worldBounds.h;
            worldBounds.y -= diff / 2;
            worldBounds.h = nuevoH;
        } else {
            // Mundo más alto que la pantalla → aumentar ancho
            var nuevoW = worldBounds.h * ratioPantalla;
            var diff = nuevoW - worldBounds.w;
            worldBounds.x -= diff / 2;
            worldBounds.w = nuevoW;
        }
    }

    function aplicarLimitesCamara() {
        if (worldBounds.w === 0) return;
        // tx cuando el borde izquierdo del mundo toca el borde izq. del viewport
        var izq = -worldBounds.x * cam.scale;
        // tx cuando el borde derecho del mundo toca el borde der. del viewport
        var der = dims.w - (worldBounds.x + worldBounds.w) * cam.scale;
        // tx cuando el borde superior del mundo toca el borde sup. del viewport
        var sup = -worldBounds.y * cam.scale;
        // tx cuando el borde inferior del mundo toca el borde inf. del viewport
        var inf = dims.h - (worldBounds.y + worldBounds.h) * cam.scale;

        if (izq > der) {
            // Mundo más ancho que el viewport → permitir paneo limitado
            cam.tx = Math.max(der, Math.min(izq, cam.tx));
        } else {
            // Mundo entra en el viewport → centrar
            cam.tx = (izq + der) / 2;
        }
        if (sup > inf) {
            cam.ty = Math.max(inf, Math.min(sup, cam.ty));
        } else {
            cam.ty = (sup + inf) / 2;
        }
    }

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
        var mediaIds = ['imagenes', 'videos', 'textos', 'sonidos', 'mapa', 'comunicacion'];
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
            case 'imagenes':
            case 'videos':
            case 'sonidos':
            case 'textos':
                renderMediosLista(id, cont);
                break;
            case 'comunicacion':
                renderComunicacion(cont);
                break;
            default:
                cont.innerHTML = '';
        }
    }

    function renderMediosLista(id, cont) {
        var tipoMap = { imagenes:'image', videos:'video', sonidos:'audio', textos:'text' };
        var tipo = tipoMap[id] || id;
        var items = (MEDIOS_FILTRADOS && MEDIOS_FILTRADOS.resultados && MEDIOS_FILTRADOS.resultados[tipo])
                    ? MEDIOS_FILTRADOS.resultados[tipo] : [];

        if (!items.length) {
            cont.innerHTML = '<div style="opacity:.2;font-size:.6rem;text-align:center;padding:.5rem">—</div>';
            return;
        }

        if (tipo === 'image') {
            // Imágenes: slideshow (una imagen a la vez, cambia src)
            if (!items.length) {
                cont.innerHTML = '<div style="opacity:.2;font-size:.6rem;text-align:center;padding:.5rem">—</div>';
                return;
            }

            SLIDESHOW.items = items;
            SLIDESHOW.index = 0;
            SLIDESHOW.cont = cont;

            var primeraUrl = 'api/servir_medio.php?id=' + items[0].id;
            var desc0 = items[0].descripcion || '';
            if (desc0.length > 120) desc0 = desc0.slice(0, 117) + '...';
            var html = '<div class="slideshow-wrap" style="display:flex;flex-direction:column;width:100%;flex:1;min-height:0;position:relative;overflow:hidden">'
                     + '<div class="slide-img-area" style="flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.1)">'
                     + '<img id="slide-actual" src="' + primeraUrl + '"'
                     + ' style="width:100%;height:100%;object-fit:cover;transition:opacity .6s ease">'
                     + '</div>'
                     + '<div id="slide-desc" style="padding:.2rem .4rem;font-size:.5rem;opacity:.65;line-height:1.3;text-align:center;border-top:1px solid rgba(var(--tr),var(--tg),var(--tb),.06);flex-shrink:0">' + desc0 + '</div>'
                     + '<div class="slide-counter" style="position:absolute;top:.3rem;right:.4rem;font-size:.45rem;opacity:.5;background:rgba(0,0,0,.4);padding:.05rem .3rem;border-radius:2px;pointer-events:none">1/' + items.length + '</div>'
                     + '</div>';
            cont.innerHTML = html;
        } else if (tipo === 'audio') {
            // Sonidos: reproductor de audio (máximo 5)
            var html = '<div style="display:flex;flex-direction:column;gap:.2rem;width:100%">';
            items.slice(0, 5).forEach(function(item) {
                var desc = item.descripcion || '';
                if (desc.length > 50) desc = desc.slice(0, 47) + '...';
                html += '<div style="display:flex;flex-direction:column;gap:.05rem;padding:.1rem 0">'
                      + (desc ? '<span style="font-size:.5rem;opacity:.5;line-height:1.2">' + desc + '</span>' : '')
                       + '<audio controls style="width:100%;height:24px" preload="metadata">'
                      + '<source src="api/servir_medio.php?id=' + item.id + '">'
                      + '</audio>'
                      + '</div>';
            });
            html += '</div>';
            cont.innerHTML = html;
        } else {
            // Otros (texto, video): lista simple
            var html = '<div style="display:flex;flex-direction:column;gap:.15rem;width:100%">';
            items.forEach(function(item) {
                var desc = item.descripcion || item.archivo || '';
                if (desc.length > 80) desc = desc.slice(0, 77) + '...';
                html += '<div style="font-size:.5rem;opacity:.5;padding:.1rem 0;line-height:1.3">' + desc + '</div>';
            });
            html += '</div>';
            cont.innerHTML = html;
        }
    }

    // ═══════════════════════════════════════════════════════
    //  TELEGRAM — bloque Comunicación
    // ═══════════════════════════════════════════════════════

    function renderComunicacion(cont, inicio, cantidad) {
        if (!MENSAJES_TELEGRAM || !MENSAJES_TELEGRAM.mensajes || !MENSAJES_TELEGRAM.mensajes.length) {
            cont.innerHTML = '';
            return;
        }
        var todos = MENSAJES_TELEGRAM.mensajes;
        if (inicio === undefined) inicio = 0;
        if (cantidad === undefined) cantidad = todos.length;
        var ventana = todos.slice(inicio, inicio + cantidad);
        var html = '<div class="tg-scroll" style="display:flex;flex-direction:column;gap:.1rem;width:100%;flex:1;min-height:0;overflow-y:auto;padding:.2rem .3rem">';
        ventana.forEach(function(m) {
            var fecha = m.date_utc || '';
            var hora = fecha.length > 16 ? fecha.slice(11, 16) : '';
            var fechaCorta = fecha.length > 10 ? fecha.slice(5, 10) : '';
            var nombre = m.from_name || 'Desconocido';
            var texto = m.text || '';
            if (texto.length > 150) texto = texto.slice(0, 147) + '...';
            var conFoto = m.fotos && m.fotos.length > 0;
            if (!conFoto && parseInt(m.has_media) === 1) {
                if (m.message_type === 'photo') conFoto = true;
            }
            var icono = '';
            if (!conFoto && parseInt(m.has_media) === 1) {
                if (m.message_type === 'photo') icono = '\uD83D\uDCF7 ';
                else if (m.message_type === 'video') icono = '\uD83C\uDFAC ';
                else if (m.message_type === 'voice') icono = '\uD83C\uDFA4 ';
                else icono = '\uD83D\uDCCE ';
            }
            html += '<div class="tg-msg" style="font-size:.5rem;line-height:1.3;border-bottom:1px solid rgba(var(--tr),var(--tg),var(--tb),.08);padding:.1rem 0">'
                  + '<span style="opacity:.5;font-size:.45rem">' + fechaCorta + ' ' + hora + '</span> '
                  + '<strong style="opacity:.85">' + nombre + '</strong> '
                  + '<span style="opacity:.65">' + (icono || (conFoto ? '\uD83D\uDCF7 ' : '')) + texto + '</span>';
            if (conFoto) {
                var fotosIds = m.fotos && m.fotos.length ? m.fotos : (m.media_ids ? m.media_ids : []);
                if (fotosIds.length) {
                    html += '<div style="display:flex;gap:.15rem;margin-top:.1rem;flex-wrap:wrap">';
                    fotosIds.forEach(function(fid) {
                        html += '<img src="api/servir_medio.php?id=' + fid + '&thumb=1"'
                              + ' style="width:auto;height:1.4rem;max-width:2.5rem;object-fit:cover;border-radius:2px;border:1px solid rgba(var(--tr),var(--tg),var(--tb),.12);cursor:pointer"'
                              + ' onclick="window.open(\'api/servir_medio.php?id=' + fid + '\',\'_blank\')"'
                              + ' loading="lazy">';
                    });
                    html += '</div>';
                }
            }
            html += '</div>';
        });
        html += '</div>';
        cont.innerHTML = html;
    }

    function cargarMensajesTelegram(municipio) {
        if (!municipio) {
            MENSAJES_TELEGRAM = null;
            renderComunicacionBlock();
            return;
        }
        MENSAJES_TELEGRAM_MUNICIPIO = municipio;
        return fetch('api/mensajes_telegram.php?municipio=' + encodeURIComponent(municipio) + '&limite=200')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                MENSAJES_TELEGRAM = data;
                renderComunicacionBlock();
            })
            .catch(function(e) {
                console.warn('Error cargando mensajes Telegram', e);
                MENSAJES_TELEGRAM = null;
                renderComunicacionBlock();
            });
    }

    function renderComunicacionBlock() {
        var bloque = document.getElementById('bloque-comunicacion');
        if (!bloque) return;
        var cont = bloque.querySelector('.bloque-contenido');
        if (!cont) return;
        renderComunicacion(cont, VENTANA_CHAT.inicio, VENTANA_CHAT.tamano);
    }

    function actualizarVentanaChat(elapsed) {
        if (!FLOW.activo) return;
        if (!MENSAJES_TELEGRAM || !MENSAJES_TELEGRAM.mensajes || !MENSAJES_TELEGRAM.mensajes.length) return;

        var total = MENSAJES_TELEGRAM.mensajes.length;
        var progreso = Math.min(1, elapsed / FLOW.duracionMs);
        var maxInicio = Math.max(0, total - VENTANA_CHAT.tamano);
        var nuevoInicio = Math.round(progreso * maxInicio);

        if (nuevoInicio === VENTANA_CHAT.ultimoInicio) return; // sin cambios

        VENTANA_CHAT.inicio = nuevoInicio;
        VENTANA_CHAT.ultimoInicio = nuevoInicio;
        renderComunicacionBlock();
    }

    // ═══════════════════════════════════════════════════════
    //  SLIDESHOW — avance automático de imágenes
    // ═══════════════════════════════════════════════════════

    function avanzarSlideshow() {
        if (!SLIDESHOW.items || !SLIDESHOW.items.length || !SLIDESHOW.cont) return;
        var img = document.getElementById('slide-actual');
        if (!img) return;

        // Calcular el próximo índice
        var prox = (SLIDESHOW.index + 1) % SLIDESHOW.items.length;

        // Fade out
        img.style.opacity = '0';

        setTimeout(function() {
            SLIDESHOW.index = prox;
            var item = SLIDESHOW.items[prox];
            img.src = 'api/servir_medio.php?id=' + item.id;
            img.style.opacity = '1';

            // Actualizar descripción
            var descEl = document.getElementById('slide-desc');
            if (descEl) {
                var txt = item.descripcion || '';
                if (txt.length > 120) txt = txt.slice(0, 117) + '...';
                descEl.textContent = txt;
            }
        }, 300);

        // Actualizar contador
        var counter = SLIDESHOW.cont.querySelector('.slide-counter');
        if (counter) {
            counter.textContent = (prox + 1) + '/' + SLIDESHOW.items.length;
        }
    }

    function reiniciarSlideshow() {
        if (!SLIDESHOW.cont || !SLIDESHOW.items.length) return;
        SLIDESHOW.index = 0;
        SLIDESHOW.ultimoAvance = 0;
        SLIDESHOW.items = SLIDESHOW.items; // mantener referencia
        var img = document.getElementById('slide-actual');
        if (img) {
            var item0 = SLIDESHOW.items[0];
            img.src = 'api/servir_medio.php?id=' + item0.id;
            img.style.opacity = '1';
            // Resetear descripción
            var descEl = document.getElementById('slide-desc');
            if (descEl) {
                var txt = item0.descripcion || '';
                if (txt.length > 120) txt = txt.slice(0, 117) + '...';
                descEl.textContent = txt;
            }
        }
        var counter = SLIDESHOW.cont.querySelector('.slide-counter');
        if (counter) counter.textContent = '1/' + SLIDESHOW.items.length;
    }

    // ═══════════════════════════════════════════════════════
    //  CHIPS: COLORES
    // ═══════════════════════════════════════════════════

    function renderChipsColores(cont) {
        var html = '<div style="display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;width:100%">';
        COLORES.forEach(function(c) {
            var activo = coloresSeleccionados.indexOf(c.nombre) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-color" data-valor="' + c.nombre + '">'
                  + '<span class="chip-bola" style="background:' + c.hex + '"></span>'
                  + c.nombre
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-colores">Todos</span>';
        html += '</div>';
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
        var html = '<div style="display:flex;flex-wrap:wrap;gap:.25rem;align-items:center;width:100%">';
        HORAS.forEach(function(h) {
            var p = PALETTAS[h];
            var hh = (h < 10 ? '0' : '') + h;
            var activo = horasSeleccionadas.indexOf(h) !== -1 ? ' activo' : '';
            html += '<button class="chip-hora' + activo + '" data-accion="toggle-hora" data-valor="' + h + '"'
                  + ' style="--chip-bg:' + p.bg.join(',') + ';--chip-txt:' + p.text.join(',') + '">'
                  + hh + ':00'
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-horas">Ninguna</span>';
        html += '</div>';
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
        var html = '<div style="display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;width:100%">';
        PROVINCIAS.forEach(function(p) {
            var activo = provinciasSeleccionadas.indexOf(p.nombre) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-provincia" data-valor="' + p.nombre + '">'
                  + p.nombre
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-provincias">Todas</span>';
        html += '</div>';
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
        var html = '<div style="display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;width:100%">';
        MUNICIPIOS.forEach(function(m) {
            var activo = municipiosSeleccionados.indexOf(m) !== -1 ? ' activo' : '';
            html += '<button class="chip' + activo + '" data-accion="toggle-municipio" data-valor="' + m + '">'
                  + m
                  + '</button>';
        });
        html += '<span class="info-filtro" id="info-municipios">Todos</span>';
        html += '</div>';
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

    function rerenderBloque(id) {
        var bloque = document.getElementById('bloque-' + id);
        if (!bloque) return;
        var cont = bloque.querySelector('.bloque-contenido');
        if (cont) renderContenidoBloque(id, cont);
    }

    // ═══════════════════════════════════════════════════════
    //  TAGS
    // ═══════════════════════════════════════════════════════

    function renderTags(cont) {
        var tags = TAGS_API || [];
        if (!tags.length) {
            cont.innerHTML = '<div style="font-size:.5rem;opacity:.4;padding:.3rem">Sin datos</div>';
            return;
        }
        var html = '<div class="tag-cloud" style="display:flex;flex-wrap:wrap;gap:.2rem .25rem;align-content:flex-start;padding:.2rem">';
        tags.forEach(function(t, i) {
            // Tamaño: peso entre 0.45rem y 0.85rem
            var peso = t.peso || 0.5;
            var size = 0.45 + peso * 0.4;
            var opacidad = 0.5 + peso * 0.5;
            html += '<span class="tag-item" style="font-size:' + size.toFixed(2) + 'rem;opacity:' + opacidad.toFixed(2) + ';cursor:default">'
                  + t.tag
                  + '</span>';
        });
        html += '</div>';
        cont.innerHTML = html;
    }

    // ═══════════════════════════════════════════════════════
    //  FLOW — iniciar, actualizar, detener
    // ═══════════════════════════════════════════════════════

    function obtenerFiltrosActivos() {
        var params = {};
        if (municipiosSeleccionados.length === 1) params.municipio = municipiosSeleccionados[0];
        if (coloresSeleccionados.length === 1) params.color = coloresSeleccionados[0];
        if (provinciasSeleccionadas.length === 1) params.provincia = provinciasSeleccionadas[0];
        return params;
    }

    function cargarMediosFiltrados() {
        var params = obtenerFiltrosActivos();
        var qs = Object.keys(params).map(function(k) {
            return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
        }).join('&');
        if (qs) qs += '&';
        qs += 'limite=20&tipo=image,audio';  // 20 imágenes para slideshow, 20 audios

        return fetch('api/medios_filtrados.php?' + qs)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                MEDIOS_FILTRADOS = data;
                // Re-renderear los bloques de medios
                renderMediaBlocks();
            })
            .catch(function(e) {
                console.warn('Error cargando medios filtrados', e);
                MEDIOS_FILTRADOS = null;
                renderMediaBlocks();
            });
    }

    function renderMediaBlocks() {
        // Re-renderear todos los bloques de medios
        ['imagenes', 'sonidos', 'textos', 'comunicacion'].forEach(function(id) {
            var bloque = document.getElementById('bloque-' + id);
            if (!bloque) return;
            var cont = bloque.querySelector('.bloque-contenido');
            if (!cont) return;
            renderContenidoBloque(id, cont);
        });
    }

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
        FLOW.ultimoScroll = -1;
        // Resetear slideshow para que arranque desde el frame 0
        SLIDESHOW.ultimoAvance = 0;
        reiniciarSlideshow();
        document.getElementById('btn-fluir').classList.add('activo');
        actualizarBotonFluir();
        // Cargar medios filtrados (no bloquear el flow)
        cargarMediosFiltrados();
        // Cargar mensajes Telegram si hay un municipio seleccionado
        if (municipiosSeleccionados.length === 1) {
            cargarMensajesTelegram(municipiosSeleccionados[0]);
        } else {
            MENSAJES_TELEGRAM = null;
            renderComunicacionBlock();
        }
    }

    function detenerFlow() {
        FLOW.activo = false;
        document.getElementById('btn-fluir').classList.remove('activo');
        document.getElementById('btn-fluir').textContent = 'Fluir';
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

        // Scroll de Telegram durante el flow
        actualizarVentanaChat(elapsed);

        // Avance del slideshow de imágenes cada ~4s
        if (elapsed - SLIDESHOW.ultimoAvance > SLIDESHOW.intervaloMs) {
            avanzarSlideshow();
            SLIDESHOW.ultimoAvance = elapsed;
        }
    }

    function actualizarBotonFluir() {
        var btn = document.getElementById('btn-fluir');
        if (!btn) return;
        btn.textContent = 'Fluir';
    }

    // ═══════════════════════════════════════════════════════
    //  GRID + DIBUJAR
    // ═══════════════════════════════════════════════════════

    function drawGrid() {
        if (worldBounds.w === 0) return;
        var spacing = Math.round(Math.max(worldBounds.w, worldBounds.h) / 14);
        spacing = Math.max(spacing, 20);

        var visLeft   = Math.max(-cam.tx / cam.scale, worldBounds.x);
        var visTop    = Math.max(-cam.ty / cam.scale, worldBounds.y);
        var visRight  = Math.min(visLeft + dims.w / cam.scale, worldBounds.x + worldBounds.w);
        var visBottom = Math.min(visTop  + dims.h / cam.scale, worldBounds.y + worldBounds.h);

        ctx.strokeStyle = rgb(paleta.accent);
        ctx.globalAlpha = 0.08;
        ctx.lineWidth = 1;
        ctx.beginPath();

        var startX = Math.floor(visLeft / spacing) * spacing;
        for (var x = startX; x <= visRight; x += spacing) {
            var sx = Math.round(x * cam.scale + cam.tx) + 0.5;
            var y0 = Math.round(visTop * cam.scale + cam.ty);
            var y1 = Math.round(visBottom * cam.scale + cam.ty);
            ctx.moveTo(sx, y0);
            ctx.lineTo(sx, y1);
        }
        var startY = Math.floor(visTop / spacing) * spacing;
        for (var y = startY; y <= visBottom; y += spacing) {
            var sy = Math.round(y * cam.scale + cam.ty) + 0.5;
            var x0 = Math.round(visLeft * cam.scale + cam.tx);
            var x1 = Math.round(visRight * cam.scale + cam.tx);
            ctx.moveTo(x0, sy);
            ctx.lineTo(x1, sy);
        }
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    function dibujar() {
        // 1. Aplicar límites de cámara
        aplicarLimitesCamara();

        // 2. Fondo completo con el color de la paleta (toda la pantalla)
        ctx.fillStyle = rgb(paleta.bg);
        ctx.fillRect(0, 0, dims.w, dims.h);

        // 3. Borde sutil del mundo
        if (worldBounds.w > 0) {
            var sx = worldBounds.x * cam.scale + cam.tx;
            var sy = worldBounds.y * cam.scale + cam.ty;
            var sw = worldBounds.w * cam.scale;
            var sh = worldBounds.h * cam.scale;
            ctx.strokeStyle = 'rgba(255,255,255,.06)';
            ctx.lineWidth = 1;
            ctx.strokeRect(sx, sy, sw, sh);
        }

        // 4. Grid (limitada a worldBounds)
        drawGrid();

        // 5. Bloques HTML
        syncBlocks();

        // 6. Indicador de datos cargados
        if (DATOS_CARGADOS) {
            ctx.fillStyle = 'rgba(255,255,255,.08)';
            ctx.font = '10px Inter, system-ui, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(DATOS_TOTAL + ' medios · ' + COLORES.length + ' colores · ' + PROVINCIAS.length + ' provincias', dims.w - 12, dims.h - 12);
        }
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
        var t = paleta.text;
        var a = paleta.accent;
        document.documentElement.style.setProperty('--tr', t[0]);
        document.documentElement.style.setProperty('--tg', t[1]);
        document.documentElement.style.setProperty('--tb', t[2]);
        document.documentElement.style.setProperty('--ar', a[0]);
        document.documentElement.style.setProperty('--ag', a[1]);
        document.documentElement.style.setProperty('--ab', a[2]);
    }

    // ═══════════════════════════════════════════════════════
    //  RESIZE
    // ═══════════════════════════════════════════════════════

    function redimensionar() {
        dims.w = window.innerWidth - 90;
        dims.h = window.innerHeight;
        canvas.width = dims.w;
        canvas.height = dims.h;
        if (worldBounds.w === 0) {
            calcularBounds();
        }
        ajustarProporcionMundo();
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
        if (worldBounds.w === 0) return;
        var cx = worldBounds.x + worldBounds.w / 2;
        var cy = worldBounds.y + worldBounds.h / 2;
        var padding = 1.05;
        var sX = dims.w / (worldBounds.w * padding);
        var sY = dims.h / (worldBounds.h * padding);
        cam.zoomMin = Math.min(sX, sY);
        cam.zoomMax = 5;
        cam.scale = Math.max(cam.zoomMin, Math.min(cam.zoomMax, cam.scale));
        cam.tx = dims.w / 2 - cx * cam.scale;
        cam.ty = dims.h / 2 - cy * cam.scale;
        actualizarZoomUI();
    }

    // ═══════════════════════════════════════════════════════
    //  CARGAR DATOS DESDE API
    // ═══════════════════════════════════════════════════════

    function cargarDatos() {
        return fetch('api/recorrido.php')
            .then(function(r) { return r.json(); })
            .then(function(datos) {
                DATOS_CARGADOS = true;
                DATOS_API = datos;
                DATOS_TOTAL = datos.total;
                console.log('API datos cargados: ' + datos.total + ' medios, ' + (datos.colores||[]).length + ' colores');
                if (datos.colores && datos.colores.length) {
                    COLORES = datos.colores.map(function(c) {
                        return { nombre: c.nombre, hex: c.hex };
                    });
                }
                var provs = {};
                datos.puntos.forEach(function(p) {
                    if (p.provincia) provs[p.provincia] = true;
                });
                var provArr = Object.keys(provs).sort();
                if (provArr.length) {
                    PROVINCIAS = provArr.map(function(n) { return { nombre: n }; });
                }
                // Extraer municipios reales
                var munMap = {};
                datos.puntos.forEach(function(p) {
                    if (p.municipio) munMap[p.municipio] = true;
                });
                var munArr = Object.keys(munMap).sort();
                if (munArr.length) MUNICIPIOS = munArr;

                console.log('COLORES:', COLORES.map(function(c){return c.nombre;}).join(', '));
                console.log('PROVINCIAS:', PROVINCIAS.map(function(p){return p.nombre;}).join(', '));
                console.log('MUNICIPIOS:', MUNICIPIOS.join(', '));
                // Re-renderear bloques de selección con datos reales
                rerenderBloque('colores');
                rerenderBloque('provincias');
                rerenderBloque('municipios');
            })
            .then(function() {
                // Cargar tags reales desde la API
                return fetch('api/tags.php?limite=40')
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data && data.tags && data.tags.length) {
                            TAGS_API = data.tags;
                            rerenderBloque('tags');
                        }
                    })
                    .catch(function(e) {
                        console.warn('Error cargando tags', e);
                    });
            })
            .catch(function(e) {
                console.warn('API no disponible, usando datos hardcodeados', e);
            });
    }

    // ═══════════════════════════════════════════════════════
    //  RESUMEN EN SIDEBAR
    // ═══════════════════════════════════════════════════════

    function renderResumen() {
        var el = document.getElementById('sidebar-resumen');
        if (!el) return;
        if (!DATOS_API) {
            el.innerHTML = '<div style="opacity:.3">—</div>';
            return;
        }
        var d = DATOS_API;
        // Calcular rango de fechas
        var fechas = [];
        var tipos = {};
        d.puntos.forEach(function(p) {
            if (p.fecha) fechas.push(p.fecha);
            var t = p.tipo || 'otro';
            tipos[t] = (tipos[t] || 0) + 1;
        });
        fechas.sort();
        var rango = '';
        if (fechas.length) {
            var ini = fechas[0].slice(5);
            var fin = fechas[fechas.length - 1].slice(5);
            rango = ini + '-' + fin;
        }
        var provCnt = PROVINCIAS.length;
        var colCnt = COLORES.length;
        var tipoHtml = '';
        ['image','video','audio'].forEach(function(t) {
            var icono = {image:'img', video:'vid', audio:'aud'}[t] || t;
            if (tipos[t]) tipoHtml += '<div style="font-size:.55rem;opacity:.5">' + icono + ' <span class="num">' + tipos[t] + '</span></div>';
        });
        el.innerHTML = '<div><span class="num">' + d.total + '</span> medios</div>'
                     + tipoHtml
                     + '<div style="margin-top:.15rem"><span class="num">' + colCnt + '</span> col · <span class="num">' + provCnt + '</span> prov</div>'
                     + '<div style="font-size:.5rem;opacity:.35;margin-top:.1rem">' + rango + '</div>';
    }

    // ═══════════════════════════════════════════════════════
    //  INICIALIZAR (después de cargar datos)
    // ═══════════════════════════════════════════════════════

    function inicializar() {
    dims.w = window.innerWidth - 60;
    dims.h = window.innerHeight;
    canvas.width = dims.w;
    canvas.height = dims.h;

    // Construir BLOQUES desde la plantilla con escala y aleatoriedad
    var escala = dims.h / 1080;
    BLOQUES_TEMPLATE.forEach(function(t) {
        var fw = 0.7 + Math.random() * 0.6; // ±30%
        var fh = 0.7 + Math.random() * 0.6;
        BLOQUES.push({
            id: t.id, tipo: t.tipo, titulo: t.titulo,
            w: Math.round(t.w * escala * fw),
            h: Math.round(t.h * escala * fh),
            mx: 0, my: 0
        });
    });

    colocarBloques();
    calcularBounds();
    ajustarProporcionMundo();
    ajustarCamaraABloques();
    dibujar();
    actualizarCSS();
    actualizarZoomUI();
    renderResumen();

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
    }

    // Arrancar: cargar datos de la API y luego inicializar
    cargarDatos().then(inicializar);

})();
