// Modular soffit track for Philips Hue Festavia permanent outdoor pucks.

// Generated from festavia_track.scad by makerworld/build.py. Dimensions in mm.

/* [Output] */
// Choose the section or a small plate to check the joint or holder fit.
output_model = "section"; // [section:Track section,joint:Joint fit test,holder:Holder and receiver test]

/* [Track section] */
// Length of the piece between its end faces (the tongues add 11 mm on the left).
piece_length = 180.00;
// Left end of the piece (seen from the street).
left_end = "tongue"; // [tongue:Tongue (joins the piece before),cap:Run start (end cap sleeve)]
// Right end of the piece.
right_end = "socket"; // [socket:Socket (joins the piece after),cap:Run end (end cap sleeve)]
// Put a light holder on this piece.
has_light = true;
// Light centre, measured from the piece centre (+ = toward the socket end).
light_offset = 32.00;
light_side = "right"; // [right:Toward socket,left:Toward tongue]
// Put a bracket receiver (mount) on this piece.
has_mount = false;
// Mount centre, measured from the piece centre.
mount_offset = 50.80;
mount_side = "left"; // [left:Toward tongue,right:Toward socket]
// Text engraved large next to the arrow (e.g. a piece number). Empty = arrow only.
label_text = "";

/* [Fit] */
// Joint fit. A0 is the fit that was printed and installed. A- and A+ (0.05 mm looser / tighter crush ribs and pin tunnel) are UNTESTED; use them only if a test joint is too tight or too loose on your printer.
fit_profile = "A0"; // [A0:A0 installed reference interfaces,loose:A- looser (fit test first),tight:A+ tighter (fit test first)]

/* [Structure] */
// Reinforced keeps full 3.2 mm walls and floor between mechanisms. As installed reproduces the lightened reference. All retain the same joint, holder and mount interfaces. New shell profiles need a physical fit test.
structure_profile = "as_installed"; // [as_installed:Installed reference shell,reinforced:Full 3.2 mm shell (fit test first),custom:Choose shell thickness below]
// Used only for Custom. Does not change the mechanical interface dimensions.
face_skin = 2.40;
side_wall = 2.40;

/* [Print settings] */
// Single nozzle: adds a 45 deg gusset under the bracket-receiver shoulders and breakaway ribs under the lever-slot roofs and the light-lock tabs, so light and mount pieces print with supports OFF. Snap the ribs out before fitting rings and levers. Off = the original geometry (needs supports).
single_nozzle = true;
// Air gap between a breakaway rib and the face it holds up (about one layer).
support_gap = 0.30;

/* [Hidden] */
part = "custom_piece";
plate_number = 1;
piece_number = 1;
length_unit = "in";
run_length = 180;
light_spacing = 16;
light_margin_min = 4;
light_placement = "auto";
first_light_offset = 10;
bracket_spacing_max = 24;
bracket_end_max = 8;
bracket_centres_mm = "";
start_gate = "blank";
end_gate = "wire";
bed_x = 256;
bed_y = 256;
engrave_numbers = true;
group_supported_pieces = true;
spare_percent = 10;
clips_flat = 0;
clips_round = 0;

/*
MIT License

Copyright (c) 2026 Festavia Track contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

$fa = 4;
$fs = 0.25;
joint_fit = fit_profile=="loose" ? -0.05 : fit_profile=="tight" ? 0.05 : 0;
FACE_SKIN = structure_profile=="as_installed" ? 1.6 : structure_profile=="reinforced" ? 3.2 : face_skin;
SIDE_WALL = structure_profile=="as_installed" ? 1.8 : structure_profile=="reinforced" ? 3.2 : side_wall;
EPS = 0.001;
_number_cut = true;   // test switch (tools/label_check.py): false keeps the number pad but skips the engraving
OV = 0.01;     // deliberate overlap for unions of faces that touch exactly in the source CAD

// ---------------------------------------------------------------- track section (fixed by the hardware)
W = 56; H = 28; WALL = 3.2;           // channel: 56 wide, 28 deep, 3.2 walls/floor
BORE = 35.2;                          // light opening (35 mm puck housing + 0.2)
SEAM = 0.4;                           // joint gap between end faces

// ---------------------------------------------------------------- basic solids (build123d helpers), EXACT coordinates
// Closed-solid rules (R23, tools/mesh_audit.py):
//  * Every planar primitive is a polyhedron. Straight-edged outlines and every extrusion coordinate are rounded to a
//    1e-6 mm grid (r6), so faces that are equal on paper are bit-identical in floating point (1.6 - 1.35 == 0.25).
//    Nearly-coplanar faces 1e-16 apart made manifold emit sliver shells that an STL loader collapsed into open edges.
//  * Arcs and circles keep their exact cos/sin values (rounding them moved points off the curve by up to 5e-7 mm).
//  * Sub-parts are placed with at(x) ($ox, applied before rounding), never translate() followed by a boolean.
//    Whole finished parts may be translated / rotated freely.
//  * Solids that are joined overlap by OV = 0.01 mm. Two places meet exactly instead, on bit-identical axis-aligned
//    planes: the joint top bands against the piece end faces, and (by construction) nothing else; an overlap there put
//    a thin coplanar strip on the long wall top whose triangulation left vertices microns apart (lost in float32 3MF).
//  * Curved regions that would overlap with coincident surfaces (the light holder) are built as one polygon per band.
$ox = 0;
function r6(v) = round(v*1e6)/1e6;
module at(x) { $ox = $ox + x; children(); }
function _sarea(p) = sum([for(i=[0:len(p)-1]) p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1]]);
// polygon pts (u,v) extruded along w from w0 to w1; map(u,v,w) -> [x,y,z]; lh = the (u,v,w) frame is left-handed
// rq = round the polygon coordinates too (straight-edged outlines); curved outlines (arcs, circles) keep their exact
// cos/sin values, which are bit-identical wherever the same angle and radius are used.
module _ext(pts, w0, w1, axis, rq=true) {
  n = len(pts); a = min(w0,w1); b = max(w0,w1);
  R = function(v) rq ? r6(v) : v;
  P = function(q, w) axis=="xy" ? [R(q[0]+$ox), R(q[1]), r6(w)] : axis=="xz" ? [R(q[0]+$ox), r6(w), R(q[1])] : [r6(w+$ox), R(q[0]), R(q[1])];
  ccw = (_sarea(pts) > 0) != (axis=="xz");      // xz: (x, z, y) is a left-handed frame
  V = concat([for(q=pts) P(q,a)], [for(q=pts) P(q,b)]);
  bot = [for(i=[0:n-1]) ccw ? i : n-1-i];
  top = [for(i=[0:n-1]) ccw ? 2*n-1-i : n+i];
  sides = [for(i=[0:n-1]) let(j=(i+1)%n) ccw ? [i, n+i, n+j, j] : [i, j, n+j, n+i]];
  polyhedron(V, concat([bot, top], sides), convexity=8);
}
module span(x0,x1,y0,y1,z0,z1) _ext([[min(x0,x1),min(y0,y1)],[max(x0,x1),min(y0,y1)],[max(x0,x1),max(y0,y1)],[min(x0,x1),max(y0,y1)]], z0, z1, "xy");
// box(): centred in x and y, z from at.z upward (build123d Align CENTER, CENTER, MIN)
module box(s, at=[0,0,0]) span(at[0]-s[0]/2, at[0]+s[0]/2, at[1]-s[1]/2, at[1]+s[1]/2, at[2], at[2]+s[2]);
// OpenSCAD's own fragment count, so tessellation matches cylinder()
function _frag(r) = $fn > 0 ? max($fn,3) : ceil(max(min(360/$fa, r*2*PI/$fs), 5));
function _circ(r, c=[0,0]) = let(n=_frag(r)) [for(i=[0:n-1]) c + r*[cos(360*i/n), sin(360*i/n)]];
module cyl(r,h,at=[0,0,0]) _ext(_circ(r,[at[0],at[1]]), at[2], at[2]+h, "xy", rq=false);
module prism_xy(pts,z0,z1) _ext(pts, z0, z1, "xy");
// polygon in the xz plane (points (x,z)) extruded from y0 to y1
module prism_xz(pts,y0,y1) _ext(pts, y0, y1, "xz");
// polygon in the yz plane (points (y,z)) extruded from x0 to x1
module prism_yz(pts,x0,x1) _ext(pts, x0, x1, "yz");
module mirror_y() mirror([0,1,0]) children();
module side(s) if(s<0) mirror([0,1,0]) children(); else children();
// Exact quarter-turn rotation (print orientation): rotate() computes cos(90) = 6e-17, which OpenSCAD 2021.01's CGAL
// carried into the bracket's 45 deg faces as a zero-width slit. Angles must be multiples of 90; the matrix is 0 / +-1.
function _cs(a) = let(k=((round(a/90))%4+4)%4) [[1,0],[0,1],[-1,0],[0,-1]][k];
function _rx(a) = let(c=_cs(a)[0], s=_cs(a)[1]) [[1,0,0],[0,c,-s],[0,s,c]];
function _ry(a) = let(c=_cs(a)[0], s=_cs(a)[1]) [[c,0,s],[0,1,0],[-s,0,c]];
function _rz(a) = let(c=_cs(a)[0], s=_cs(a)[1]) [[c,-s,0],[s,c,0],[0,0,1]];
module rot90(r) {
  assert(r[0]%90==0 && r[1]%90==0 && r[2]%90==0, "rot90: multiples of 90 deg only");
  R = _rz(r[2]) * _ry(r[1]) * _rx(r[0]);      // same order as rotate([x,y,z])
  multmatrix([[R[0][0],R[0][1],R[0][2],0],[R[1][0],R[1][1],R[1][2],0],[R[2][0],R[2][1],R[2][2],0],[0,0,0,1]]) children();
}
// annular sector between angles a0..a1 (deg), z..z+h (build123d sector())
// Arc vertices sit on a fixed absolute angle grid (SECTOR_STEP) plus the end angles, so sectors that share a radius
// share their vertices there and union without slivers.
SECTOR_STEP = 3;   // 3 deg arc grid: <= 0.014 mm chord error at r 40; keeps light pieces < 10 s in OpenSCAD 2021.01 (CGAL)
function _arc(r,a0,a1) = [for(a=concat([a0],[for(k=[ceil(a0/SECTOR_STEP+1e-9):1:floor(a1/SECTOR_STEP-1e-9)]) k*SECTOR_STEP],[a1])) r*[cos(a),sin(a)]];
module sector(ri,ro,a0,a1,z,h)
  _ext(concat(_arc(ro,a0,a1), [for(q=[for(i=[len(_arc(ri,a0,a1))-1:-1:0]) _arc(ri,a0,a1)[i]]) q]), z, z+h, "xy", rq=false);

// Extruded profile (points (y,z), counter-clockwise or clockwise, simple, orthogonal edges are not required)
// from x0 to x1 with 45 deg chamfers of size c on the end faces. f0/f1: per-edge flags (edge i = pts[i]->pts[i+1]);
// 1 = chamfer that edge on that end, 0 = leave it sharp.
function _lnorm(a,b,sg) = let(d=b-a, l=norm(d)) sg*[-d[1],d[0]]/l;
function _area2(p) = sum([for(i=[0:len(p)-1]) p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1]]);
function sum(v) = len(v)==0 ? 0 : v[0] + sum([for(i=[1:1:len(v)-1]) v[i]]);
function _inset(p,c,f) = let(n=len(p), sg=_area2(p)>0?1:-1)
  [for(i=[0:n-1]) let(
     a=p[(i-1+n)%n], v=p[i], b=p[(i+1)%n],
     n1=_lnorm(a,v,sg), n2=_lnorm(v,b,sg), c1=c*f[(i-1+n)%n], c2=c*f[i],
     det=n1[0]*n2[1]-n1[1]*n2[0],
     d=[(c1*n2[1]-c2*n1[1])/det, (n1[0]*c2-n2[0]*c1)/det])
   v+d];
module chamfered_prism_yz(p, x0, x1, c, f0, f1) {
  n=len(p);
  r0=_inset(p,c,f0); r1=_inset(p,c,f1);
  rings=[[x0,r0],[x0+c,p],[x1-c,p],[x1,r1]];
  pts=[for(r=rings) for(q=r[1]) [r6(r[0]+$ox),r6(q[0]),r6(q[1])]];
  sg=_area2(p)>0?1:-1;
  side=[for(k=[0:2]) for(i=[0:n-1]) let(a=k*n+i, b=k*n+(i+1)%n, c2=(k+1)*n+(i+1)%n, d=(k+1)*n+i)
        sg<0 ? [a,b,c2,d] : [a,d,c2,b]];
  cap0=[for(i=[0:n-1]) sg<0 ? n-1-i : i];
  cap1=[for(i=[0:n-1]) sg<0 ? 3*n+i : 4*n-1-i];
  polyhedron(pts, concat([cap0],side,[cap1]), convexity=6);
}

// ---------------------------------------------------------------- channel
module channel(length, cx=0) {
  box([length,W,WALL],[cx,0,0]);
  for(sy=[-1,1]) box([length,WALL,H],[cx,sy*(W-WALL)/2,0]);
}

// ---------------------------------------------------------------- light holder (turn-to-lock ring, v2 holder)
LOCK_A = 115;                                   // ring stop pin position (deg)
AX = 25.2*cos(LOCK_A); AY = 25.2*sin(LOCK_A);
LUGS = [25,115,205,295];                        // ring lug / holder post angles

// Holder sectors (posts, bayonet tabs and stops of v0.4-v0.6.1, the v2 fill of fix_light_holder.py and the
// single-nozzle stop fill), built from their closed-form union instead of overlapping sectors: per z band, each lug
// is ONE polar polygon (angle intervals with an r range each). All arcs of a lug use the same vertex angles (3 deg grid
// + the lug's break angles), so stacked bands share bit-identical vertices and no two solids have coincident curved
// or radial faces. (Overlapping sectors with the same radius but different end angles left vertices microns apart,
// which a float32 3MF / binary STL merges into open edges.)
//   band        angle intervals [from, to, r_in, r_out] relative to the lug angle a
// The lowest band starts OV inside the floor. Bands meet each other exactly, on bit-identical z planes, and every
// radial edge is subdivided at all band radii (HOLDER_RADII), so two bands share every vertex where they meet. (An OV
// overlap between bands put the upper band's radial faces into the lower band's slanted radial planes through points
// that cannot be exactly collinear; OpenSCAD 2021.01's 3MF writer then split vertices there.)
HOLDER_RADII = [19.5, 22.15, 25.15, 28, 40];
HOLDER_BANDS = [
  [3.2-OV, 12.8, [[7,10,22.15,40],[10,34,19.5,40]]],               // v2 fill under tabs and stops, posts, webs
  [12.8, 14.2, [[7,34,25.15,40]]],                                 // posts + webs (gap under the ring stops)
  [14.2, 19,   [[7,29,25.15,40],[29,34,22.15,40]]],                // + ring stops
  [19, 25.2,   [[7,10,25.15,40],[10,34,22.15,40]]]];               // + bayonet tabs, raised to 25.2 by the v2 fix
HOLDER_BANDS_SN = [                                                // single nozzle: stop fill closes the 12.8-14.2 gap
  [3.2-OV, 12.8, [[7,10,22.15,40],[10,34,19.5,40]]],
  [12.8, 19,   [[7,29,25.15,40],[29,34,22.15,40]]],
  [19, 25.2,   [[7,10,25.15,40],[10,34,22.15,40]]]];
function _lug_angles(a) = _qsort1(concat([for(o=[7,10,29,34]) a+o],
  [for(k=[ceil((a+7)/SECTOR_STEP+1e-9):1:floor((a+34)/SECTOR_STEP-1e-9)]) k*SECTOR_STEP]));
function _dedupe(p) = [for(i=[0:len(p)-1]) if(i==0 || norm(p[i]-p[i-1]) > 1e-9) p[i]];
// radii strictly between r0 and r1, in the order from r0 to r1
function _rbetween(r0, r1) = r0 < r1 ? [for(r=HOLDER_RADII) if(r > r0+1e-9 && r < r1-1e-9) r]
                                     : [for(i=[len(HOLDER_RADII)-1:-1:0]) let(r=HOLDER_RADII[i]) if(r < r0-1e-9 && r > r1+1e-9) r];
function _pt(r, t) = r*[cos(t), sin(t)];
function _polar_poly(a, ivs) = let(A=_lug_angles(a), n=len(ivs),
  inI = function(t, i) t >= a+ivs[i][0]-1e-9 && t <= a+ivs[i][1]+1e-9,
  outer = [for(i=[0:n-1]) each concat([for(t=A) if(inI(t,i)) _pt(ivs[i][3], t)],
            i < n-1 ? [for(r=_rbetween(ivs[i][3], ivs[i+1][3])) _pt(r, a+ivs[i][1])] : [])],
  endr  = [for(r=_rbetween(ivs[n-1][3], ivs[n-1][2])) _pt(r, a+ivs[n-1][1])],
  inner = [for(i=[n-1:-1:0]) each concat([for(j=[len(A)-1:-1:0]) let(t=A[j]) if(inI(t,i)) _pt(ivs[i][2], t)],
            i > 0 ? [for(r=_rbetween(ivs[i][2], ivs[i-1][2])) _pt(r, a+ivs[i][0])] : [])],
  startr = [for(r=_rbetween(ivs[0][2], ivs[0][3])) _pt(r, a+ivs[0][0])])
  _dedupe(concat(outer, endr, inner, startr));
module holder_sectors(sn=false) {
  FILL_TOP = 12.8; TOP = 25.2;
  K7 = [7.0,15.09,FILL_TOP-WALL]; K7_AT = [AX,(10.0+AY-2.25+4.5)/2,WALL];   // the v2 fill keeps the detent pocket open
  difference() {
    intersection() {
      union() for(a=LUGS, b=(sn ? HOLDER_BANDS_SN : HOLDER_BANDS)) _ext(_polar_poly(a, b[2]), b[0], b[1], "xy", rq=false);
      box([60,56,TOP]);
    }
    // fix_light_holder.py keep-outs (they only ever cut the v2 fill; the posts are restored below)
    box([5.3,4.3,22],[AX,AY,8.6]);
    box([7.0,9.0,1.9],[AX,AY-2.25,9.1]);
    cyl(2.95,30,[AX,AY,14.2]);
    box([9+1.0,3.6+1.0,8],[AX,AY-0.2,23.7]);
    box([5,3,0.7],[AX+5.2,AY-0.2,23.3]);
    box(K7, K7_AT);
    box([49+2,20+2,TOP]);
  }
  // the 115 deg post inside the detent keep-out is v0.6.1 holder material, not v2 fill: put it back, minus the
  // v0.6 detent pocket and pin channel that cut it in the original (122-124 deg)
  difference() {
    intersection() {
      _ext(_polar_poly(115, [[7,34,25.15,28]]), WALL-OV, FILL_TOP, "xy", rq=false);
      box(K7, K7_AT);
    }
    holder_cuts_b();
  }
}

// cuts of the v0.6.1 holder that also reach the channel (light bore, stop-screw head recess in the wall, pin channel)
module holder_cuts_a() {
  prism_xy([for(i=[0:5]) [AX,AY] + 5.8/sqrt(3)*[cos(30+60*i), sin(30+60*i)]], 8, 8+2.7);   // M3 nut pocket
  box([5.8,6,2.7],[AX,AY-3,8]);
  cyl(2.95,H-14.2+1,[AX,AY,14.2]);
  cyl(1.7,11,[AX,AY,4.0]);
}
module holder_cuts_b() { box([5.3,4.3,22],[AX,AY,8.6]); box([7.0,9.0,1.9],[AX,AY-2.25,9.1]); }
module holder_channel_cuts() { cyl(BORE/2, WALL+1, [0,0,-0.1]); holder_cuts_a(); holder_cuts_b(); }
// ch = with its own 60 mm channel (stand-alone section); in a track piece holder_channel_cuts() go to the piece's
// continuous channel instead. Same solid: (C - bore + X) - A + Y - B = (C - bore - A - B) + ((X - A) + Y - B).
module lc6_holder(sn=false, ch=true) {          // v0.6.1 LC6_holder (light_c v0.4 + tab stops v0.5 + pin pocket v0.6) + v2 fix
  difference() {
    union() {
      difference() {
        union() {
          // light_base
          if(ch) difference() { channel(60); cyl(BORE/2, WALL+1, [0,0,-0.1]); }
          for(sx=[-1,1],sy=[-1,1]) box([6,5,8-WALL+OV],[sx*21.5,sy*6.8,WALL-OV]);   // OV: into the floor
          box([11,7.6,14.2-WALL+OV],[AX,AY,WALL-OV]);
        }
        holder_cuts_a();
      }
      // v0.5 blocks beside the puck's mounting tabs (tab width 20 + 2 x 0.2)
      for(sx=[-1,1],sy=[-1,1]) box([6,2.4,9.6+OV],[sx*21.5,sy*(20/2+0.2+1.2),3.2-OV]);
      // v0.6 guided stop-pin block
      box([11,7.6,11+OV],[AX,AY,3.2-OV]);
    }
    holder_cuts_b();
  }
  // posts, tabs, stops and the v2 fill. lc6's own cuts above never reach them (the sectors start at 122 deg at the
  // 115 deg lug, the cuts end by 121.7 deg), so adding them afterwards gives the same solid.
  holder_sectors(sn);
}
module holder_fix_add() {}                      // now part of holder_sectors()
module holder_stop_fill() {}                    // now part of holder_sectors(sn = true)

// ---------------------------------------------------------------- bracket receiver on the track (v0.7 M7 track)
// ch = with its own 60 mm channel (stand-alone section); in a track piece the piece's continuous channel is used and
// receiver_cuts() are applied to it (no overlapping coplanar channel strips).
module receiver_cuts() for(sy=[-1,1]) {
  box([32.6,5.6,4.4],[0,sy*22.8,19.8]);
  box([12.6,8.2,10],[-10,sy*24.1,19.8]);
  prism_xz([[-25,28.5],[-16.3,19.8],[-16.3,28.5]], sy*24.1-4.1, sy*24.1+4.1);
  for(x=[-24,24]) box([4.5,4,3.0],[x,sy*26.5,25.8]);
}
module mount_receiver(ch=true) {
  difference() {
    union() {
      if(ch) channel(60);
      for(sy=[-1,1]) {
        box([40,7.6,9.2],[0,sy*24.2,18.8]);
        prism_xy([[20,sy*20.4],[24.4,sy*24.8],[24.4,sy*(24.8+OV)],[20,sy*(24.8+OV)]],18.8,28);   // OV into the wall
      }
    }
    receiver_cuts();
  }
}

// ---------------------------------------------------------------- single-nozzle features (phase 2)
// Receiver frame: 45 deg gusset from the side wall up to the shoulder underside (z 18.8). Nothing bears on that face
// (the lever toes run in the slot above it), so it is designed out instead of supported.
module receiver_gusset() for(sy=[-1,1]) side(sy) {
  tri = [[24.8+OV,14.4],[24.8+OV,18.8+OV],[20.4,18.8+OV]];
  prism_yz(tri, -20, 20);
  hull() {                                      // under the tapered end of the shoulder (x 20 .. 24.4)
    prism_yz(tri, 20-EPS, 20);
    span(24.4-EPS, 24.4, 24.8, 24.8+OV, 18.8, 18.8+OV);
  }
}
// Breakaway comb under each lever-slot roof (z 24.2, x -3.7 .. 16.3): a spine and 7 fins standing on the slot floor,
// support_gap below the roof and 0.3 mm clear of the walls. Pull it out through the open slot side before fitting levers.
module receiver_ribs() for(sy=[-1,1]) side(sy) {
  zt = 24.2 - support_gap; z0 = 19.8 - OV;
  span(-3.4, 16.0, 20.6, 21.4, z0, zt);
  for(i=[0:6]) let(x=-3.4+i*3.1) span(x, x+0.8, 20.6, 25.3, z0, zt);
}
// Holder frame: fill the 1.4 mm space under each ring stop (z 12.8 .. 14.2, a+29 .. a+34). The ring lugs never
// reach that angle (locked they end at a+28), so it is designed out.
module holder_stop_fill() for(a=LUGS) sector(22.17, 25.15+OV, a+29, a+34, 12.8-OV, 14.2-12.8+2*OV, k=8);   // r 22.17: own cylinder (22.15 and 22.16 are taken)
// Breakaway arc rib under each bayonet tab (tab underside z 19.0 over r 22.15 .. 25.15), standing on the v2 fill at
// z 12.8; reach it from the bore and pull it out before fitting the ring. At the stop-pin lug (115 deg) the fill
// is open toward the centre up to ~127.5 deg and the stop-pin block face (y 19.04) is 0.09 mm away at 128 deg, so
// that rib starts at 129.5 deg (0.7 mm clear of the block, on the fill).
module holder_ribs() for(a=LUGS) {
  a0 = (a==115) ? max(a+10.75, 129.5) : a+10.75;
  sector(23.25, 24.05, a0, a+28.25, 12.8-OV, 19-support_gap-12.8+OV);
}

// ---------------------------------------------------------------- concept A joint (fit variant A0)
ZTOP = 20.0; X_L = 14.0; X_R = 14.0; Y_IN = 8.0;
YT = 12.7; NECK = 3.4; HEAD_D = 6.0; HEAD_X = -7.6;
C_T = 0.10; C_RAMP = 0.20;
YB = 20.2; BAR_T = 3.0; C_SLOT = 0.075;
BAR_X0 = -13.9; BAR_X1 = 14.3; BAR_Z0 = 4.0; BAR_Z1 = 17.0; LEG_Z0 = 1.8; LEG_L = 3.0;
C_LEG = 0.10; I_LEG = 0.20;
BUMPS = [-11.6,-4.4,4.8,12.0]; C_ROOF = 0.10; I_BUMP = 0.30;
FLARE_DEG = 35.0;

module tongue_outline(c=0) {
  xf = HEAD_X+HEAD_D/2; hw = NECK/2; HW = HEAD_D/2; xe = xf-(HW-hw)/tan(FLARE_DEG);
  offset(delta=c) union() {
    polygon([[SEAM+0.2,YT-hw],[xf,YT-hw],[xe,YT-HW],[HEAD_X,YT-HW],[HEAD_X,YT+HW],[xe,YT+HW],[xf,YT+hw],[SEAM+0.2,YT+hw]]);
    intersection() {
      translate([HEAD_X,YT]) circle(r=HW, $fn=128);
      translate([HEAD_X-HW-1,YT-HW-1]) square([HW+1,2*HW+2]);
    }
  }
}
// everything below the 45 deg plane z = 3.2 + (0.4 - x) + zoff
module bevel_cut(zoff, x0=-30, x1=SEAM+0.2) {
  z_at = function(x) 3.2+(SEAM-x)+zoff;
  prism_xz([[x0,-1],[x1+1,-1],[x1+1,z_at(x1+1)],[x0,z_at(x0)]],-30,30);
}
module tongue() difference() { translate([$ox,0,0]) linear_extrude(25.2) tongue_outline(0); bevel_cut(0); }

function pin_section(c_top=0, c_side=0, dz=0) =
  let(y0=17.45-c_side, y1=22.95+c_side, zb=17.2-c_top+dz, zs=19.45+c_top*sqrt(2)+dz, apex=22.2+c_top*sqrt(2)+dz)
  [[y0,zb],[y1,zb],[y1,zs-(y1-22.95)],[20.2,apex],[y0,zs-(17.45-y0)]];

module a_cutters(dv) {        // +y side; slot, leg holes, pin tunnel
  e = 0;
  span(BAR_X0-2,BAR_X1+2, YB-BAR_T/2-C_SLOT-e, YB+BAR_T/2+C_SLOT+e, BAR_Z0, 26);
  span(BAR_X0-2,BAR_X0+LEG_L+C_LEG+e, YB-BAR_T/2-C_SLOT-e, YB+BAR_T/2+C_SLOT+e, LEG_Z0-0.2, BAR_Z0+0.01);
  span(BAR_X1-LEG_L-C_LEG-e,BAR_X1+2, YB-BAR_T/2-C_SLOT-e, YB+BAR_T/2+C_SLOT+e, LEG_Z0-0.2, BAR_Z0+0.01);
  prism_yz(pin_section(C_ROOF+e,0.2+e,-dv), -X_L-0.5, SEAM+X_R+0.5);
}
module a_rib(which, dv) {     // +y side; crush rib on the seam-side wall of a leg hole
  tip = 0-I_LEG-dv;
  x_face = which=="L" ? BAR_X0+LEG_L : BAR_X1-LEG_L;
  dirx = which=="L" ? 1 : -1;
  a = x_face+dirx*tip; base = x_face+dirx*(C_LEG+0.6);
  prism_xy([[a,YB],[base,YB-0.4],[base,YB+0.4]], LEG_Z0, BAR_Z0);
}
// top band of the seam (z >= ZTOP): the end-face cross-section, extended by 0.2 mm (x0..x1)
module top_band(x0,x1) {
  for(s=[-1,1]) {
    span(x0,x1, s*Y_IN, s*24.8, ZTOP, 25.2);
    span(x0,x1, s*24.8, s*28, ZTOP, H);
  }
}
// socket end, joint frame: children() = the piece placed with its right end face at x = 0
module socket_end(dv) {
  difference() {
    union() {
      children();
      for(s=[-1,1]) span(-X_L,0, s*Y_IN, s*24.8, 1.6, 25.2);
      top_band(0, 0.2);   // meets the end face exactly (bit-identical r6 plane); an OV overlap here put a thin coplanar strip on the long wall top and its triangulation left vertices microns apart
    }
    for(s=[-1,1]) side(s) {
      intersection() {
        difference() { translate([$ox,0,0]) linear_extrude(26) tongue_outline(C_T); bevel_cut(-C_RAMP*sqrt(2)); }
        span(-X_L,0.2+0.01,-30,30,0,30);   // to x = 0.2 (the band face); 0.01 past it so no coplanar skin is left
      }
      a_cutters(dv);
    }
  }
  for(s=[-1,1]) side(s) a_rib("L",dv);
}
// tongue end, joint frame: children() = the piece placed with its left end face at x = 0.4
module tongue_end(dv) {
  difference() {
    union() {
      children();
      for(s=[-1,1]) span(SEAM,SEAM+X_R, s*Y_IN, s*24.8, 1.6, 25.2);
      top_band(0.2, SEAM);   // exact contact with the end face, as above
      for(s=[-1,1]) side(s) tongue();
    }
    for(s=[-1,1]) side(s) a_cutters(dv);
  }
  for(s=[-1,1]) side(s) a_rib("R",dv);
}

// ---------------------------------------------------------------- track piece
// sort / merge helpers for the wall-lightening zones
function _qsort(v) = len(v)<=1 ? v : let(p=v[floor(len(v)/2)][0])
  concat(_qsort([for(a=v) if(a[0]<p) a]), [for(a=v) if(a[0]==p) a], _qsort([for(a=v) if(a[0]>p) a]));
function _merge(v, i=0, acc=[]) = i>=len(v) ? acc :
  (len(acc)>0 && v[i][0] <= acc[len(acc)-1][1])
    ? _merge(v, i+1, concat([for(k=[0:1:len(acc)-2]) acc[k]], [[acc[len(acc)-1][0], max(acc[len(acc)-1][1], v[i][1])]]))
    : _merge(v, i+1, concat(acc,[v[i]]));
function _gaps(z, lo, hi) = let(n=len(z))
  [ if(n==0) [lo,hi],
    if(n>0 && z[0][0]>lo) [lo,z[0][0]],
    for(i=[0:1:n-2]) [z[i][1], z[i+1][0]],
    if(n>0 && z[n-1][1]<hi) [z[n-1][1],hi] ];

module arrow_cut(x,y,z) prism_xy([for(q=[[-4,-.6],[0,-.6],[0,-2],[4,0],[0,2],[0,.6],[-4,.6]]) q+[x,y]], z+0.02-0.27, z+0.02);

// Large build-order number + arrow (phase 2): digits NUM_H tall, NUM_D deep, in the inside floor (flat, faces up
// when printing). A 3.2 mm floor pad (12 mm wide) sits under them. Layout along x from the label centre lx:
// text [lx - tw/2, lx + tw/2], arrow [lx + tw/2 + 2, lx + tw/2 + 14].
NUM_H = 8.5; NUM_D = 0.8; NUM_PAD_Y = 12;
function num_w(t) = 6.6*len(t);
function num_extent(lx, t) = [lx - num_w(t)/2 - 2, lx + num_w(t)/2 + 16];
// lay = [number centre, arrow centre]; together normally, split over two free floor strips on short light pieces
module number_cut(lay, t) {
  translate([lay[0]+$ox,0,WALL-NUM_D]) linear_extrude(NUM_D+0.05)
    resize([0,NUM_H],auto=[true,true]) text(t, size=10, halign="center", valign="center", font="Liberation Sans:style=Bold");
  prism_xy([for(q=[[-6,-1.3],[0,-1.3],[0,-3.6],[6,0],[0,3.6],[0,1.3],[-6,1.3]]) q+[lay[1],0]], WALL-NUM_D, WALL+0.05);
}
function lay_pads(lay, t) = abs(lay[1] - (lay[0]+num_w(t)/2+8)) < 1e-6 ? [num_extent(lay[0], t)]
  : [[lay[0]-num_w(t)/2-2, lay[0]+num_w(t)/2+2], [lay[1]-8, lay[1]+8]];
// free floor intervals of a piece outside the feature windows (+-31)
function free_iv(L, fs) = let(z=_merge(_qsort([for(f=fs) [max(f-31,-L/2+1), min(f+31,L/2-1)]])))
  [for(g=_gaps(z, -L/2+1, L/2-1)) if(g[1]>g[0]) g];
function label_layout(L, lights, mounts, t) = let(c=label_pos(L, lights, mounts, t))
  c != undef ? [c, c+num_w(t)/2+8] :
  let(iv=_qsort([for(g=free_iv(L, lights)) [-(g[1]-g[0]), g]]), n=[for(e=iv) if(-e[0] >= num_w(t)+4) e[1]],
      a=[for(e=iv) if(-e[0] >= 16 && (len(n)==0 || e[1]!=n[0])) e[1]])
  len(n)>0 && len(a)>0 ? [(n[0][0]+n[0][1])/2, (a[0][0]+a[0][1])/2] : undef;
// first label centre (Dylan's 0 / -30 first, then outward) whose extent stays on the piece and off the light windows
// (and off the mount windows if possible)
function label_pos(L, lights, mounts, t) = let(
  cands = concat([0,-30,30],[for(i=[1:1:floor(L/2)]) each [-i,i]]),
  ok = function(x, fs) let(e=num_extent(x,t)) e[0] >= -L/2+1 && e[1] <= L/2-1 &&
                       len([for(f=fs) if(e[1] > f-31 && e[0] < f+31) 1]) == 0,
  a = [for(x=cands) if(ok(x, concat(lights,mounts))) x],
  b = [for(x=cands) if(ok(x, lights)) x])
  len(a)>0 ? a[0] : len(b)>0 ? b[0] : undef;

module track_v1(L, lights, mounts, first, last, label_x, label, sn=false) {
  big = label != "";
  left = -L/2; right = L/2;
  feats = concat(lights, mounts);
  // wall reduction zones (v0.8.2) and floor masks
  zones = concat([for(x=feats) [x-33,x+33]],
                 first ? [[left,left+27]] : [[left,left+22]],
                 last ? [[right-27,right]] : [[right-22,right]]);
  merged = _merge(_qsort([for(z=zones) [max(z[0],left), min(z[1],right)]]));
  gaps = [for(g=_gaps(merged,left,right)) if(g[1]-g[0]>=8) g];
  union() {
    difference() {
      // integrated production section (production-v08 build_parts)
      union() {
        difference() {                          // one continuous channel; the features' channel cuts applied to it
          channel(L);
          for(x=lights) at(x) holder_channel_cuts();
          for(x=mounts) at(x) receiver_cuts();
        }
        for(x=lights) at(x) lc6_holder(sn, ch=false);
        for(x=mounts) at(x) { mount_receiver(ch=false); if(sn) receiver_gusset(); }
      }
      // direction arrow (points from the tongue end to the socket end), with the large number if any
      if(big) { if(_number_cut) number_cut(label_x, label); } else arrow_cut(label_x+13,0,WALL);   // label_x = layout if big
      // lightened floor: 1.6 mm face skin except under the mechanisms
      if(FACE_SKIN < WALL) difference() {
        box([L+2,49.6,WALL-FACE_SKIN],[0,0,FACE_SKIN]);
        for(x=lights) box([60,60,32],[x,0,0]);
        if(!first) for(sy=[-1,1]) box([18,15,4],[left+9,sy*20.2,0]);
        if(!last)  for(sy=[-1,1]) box([18,15,4],[right-9,sy*20.2,0]);
        if(first) box([26,60,32],[left+13,0,0]);
        if(last)  box([26,60,32],[right-13,0,0]);
        if(big) for(e=lay_pads(label_x,label)) box([e[1]-e[0],NUM_PAD_Y,4],[(e[0]+e[1])/2,0,0]);
        else box([34,8,4],[label_x+5,0,0]);
      }
      // lightened side walls: 1.8 mm between the mechanisms
      if(SIDE_WALL < WALL) for(g=gaps, sy=[-1,1]) let(a=g[0], c=g[1], inner=28-SIDE_WALL)
        prism_xy([[a,sy*24.7],[a+3,sy*inner],[c-3,sy*inner],[c,sy*24.7]], WALL, WALL+24.9);
    }
  }
}

// Layout rules of the production plan (production-v08 plan_sections.py), checked for every piece:
//   a light/mount centre >= 50.6 mm from a joint end face (joint centre 0.2 beyond it: >= 50.8 = 2 in),
//   >= 53.6 mm from a cap end face (30 mm feature half-width + 21.6 mm cap insert + 2 mm),
//   light and mount windows (60 mm each) >= 2 mm apart, 30 < piece length <= 240.
function feature_ok(x, L, first, last) =
  (L/2 + x >= (first ? 53.6 : 50.6) - 1e-6) && (L/2 - x >= (last ? 53.6 : 50.6) - 1e-6);
module track_piece(L=piece_length, lights=[], mounts=[], left_kind="tongue", right_kind="socket", dv=0, label="", sn=false) {
  first = left_kind=="cap"; last = right_kind=="cap";
  assert(L > 30 && L <= 240, str("piece_length must be in (30, 240] mm, got ", L));
  assert((!first && !last) || L>=47-1e-6, "a cap end needs at least 47 mm of track to clear the joint block");
  for(x=concat(lights,mounts)) assert(feature_ok(x,L,first,last),
    str("feature at ", x, " mm is too close to an end of a ", L, " mm piece (>= 50.6 mm from a joint end, >= 53.6 mm from a cap end)"));
  for(a=lights, b=mounts) assert(abs(a-b) >= 62-1e-6, str("light at ", a, " and mount at ", b, " overlap (need >= 62 mm apart)"));
  label_x = label=="" ? (len([for(x=lights) if(abs(x)<38) x])>0 ? -30 : 0) : label_layout(L, lights, mounts, label);
  assert(label_x != undef, str("no room for the number on a ", L, " mm piece"));
  module body() track_v1(L, lights, mounts, first, last, label_x, label, sn);
  module with_tongue() {
    if(!first) at(-L/2-SEAM) tongue_end(dv) at(L/2+SEAM) body();
    else body();
  }
  if(!last) at(L/2) socket_end(dv) at(-L/2) with_tongue();
  else with_tongue();
  if(sn) {                                      // breakaway ribs: added last, nothing cuts them
    for(x=lights) at(x) holder_ribs();
    for(x=mounts) at(x) receiver_ribs();
  }
}

// ---------------------------------------------------------------- splice bar
module splice_bar() {      // joint frame, +y side, as printed (crush ridges sharp)
  bump_top = 17.2+C_ROOF*sqrt(2)+I_BUMP;
  prism_xz([[BAR_X0,LEG_Z0],[BAR_X0+LEG_L,LEG_Z0],[BAR_X0+LEG_L,BAR_Z0],[BAR_X1-LEG_L,BAR_Z0],[BAR_X1-LEG_L,LEG_Z0],
            [BAR_X1,LEG_Z0],[BAR_X1,BAR_Z1],[BAR_X0,BAR_Z1]], YB-BAR_T/2, YB+BAR_T/2);
  for(x=BUMPS) prism_xz([[x-0.4,BAR_Z1-0.3],[x+0.4,BAR_Z1-0.3],[x,bump_top]], YB-BAR_T/2, YB+BAR_T/2);
}

// ---------------------------------------------------------------- JB6 cross pin (v0.6), joint frame
module jb6_pin() {
  difference() {
    union() {
      prism_yz([for(q=[[-2.8,0],[2.8,0],[2.8,2.2],[0,5],[-2.8,2.2]]) q+[20.2,17.2]], -14.25-OV, -14.25+30.55);   // OV into the head
      box([3.4,9,7],[-15.95,20.2,17.2]);
      for(sy=[-1,1]) prism_xy([[14.65,20.2+sy*2.79],[14.65,20.2+sy*3.25],[15.25,20.2+sy*3.25],[16.3,20.2+sy*2.79]],17.2,19.2);  // 2.79: 0.01 into the shaft
    }
    box([13,1.2,6],[10.1,20.2,17.1]);
  }
}

// ---------------------------------------------------------------- bracket (v0.7.2 M72_bracket), mount frame
// OV into the key box; the 45 deg face moved OV outward: the key box corner (cx+2, 24.9) lay exactly on it (edge-on-face
// contact, a sliver in OpenSCAD 2021.01 / CGAL)
module bracket_locator_cap(cx,sy) prism_xy([[cx-4,sy*24],[cx+1.1+OV,sy*24],[cx+5.6+OV,sy*28.5],[cx-4,sy*28.5]],28.2-OV,29.0);
module bracket_key(x,sy) {
  box([4,4,1],[x,sy*26.9,27.2]);
  hull() {
    span(x-1.4, x+1.4, sy*27.2-1.4, sy*27.2+1.4, 26, 26+EPS);
    span(x-2, x+2, sy*26.9-2, sy*26.9+2, 27.2-EPS, 27.2+OV);   // OV into the key box above
  }
}
module bracket() {
  ENTRY_KEY_X = -5.95; PIN_X = -17.8;
  difference() {
    union() {
      difference() {
        union() {
          // v0.7 M7_bracket
          difference() {
            union() {
              difference() {
                union() {
                  box([60,69,5],[0,0,33]);
                  for(sy=[-1,1]) box([60,6.25,20],[0,sy*31.375,18]);
                }
                for(sy=[-1,1]) box([46.3,3.7,3.8],[-6.85,sy*29.85,29.0]);
              }
              for(sy=[-1,1], x=[-24,24]) { box([8,4.5,.8],[x,sy*26.25,28.2]); bracket_key(x,sy); }
            }
            box([46.5,8,3.8],[-6.95,32.0,29.0]);
            for(cx=[3.0,23.0]) box([4.6,2.0,3.8],[cx,34.1,29.0]);
            for(x=[-23,23]) { cyl(2.3,6,[x,0,32.8]); cyl(4.5,3.8,[x,0,32.9]); }
            cyl(1.65,9.4,[PIN_X,-30.0,28.8]);
            cyl(3.2,2.2,[PIN_X,-30.0,36.0]);
          }
        }
        // v0.7.2: tapered locator ledges
        for(sy=[-1,1], cx=[-24,24]) box([8,4.5,.8],[cx,sy*26.25,28.2]);
      }
      for(sy=[-1,1]) {
        for(cx=[-24,24]) bracket_locator_cap(cx,sy);
        bracket_locator_cap(ENTRY_KEY_X,sy);
        bracket_key(ENTRY_KEY_X,sy);
      }
    }
    box([46.5,8,3.8],[-6.95,-32.0,29.0]);
    arrow_cut(12,12,38);     // top arrow points the same way as the track arrows
  }
}

// ---------------------------------------------------------------- lever (v0.7.1 lever + v0.7.2 dual grip), mount frame
module lever() {
  prof = [[-31.25,32.4],[-31.25,29.4],[-20,29.4],[-20,23.8],[-25.2,23.8],[-25.2,20.2],[-16.6,20.2],[-16.6,29.4],
          [16.6,29.4],[16.6,20.2],[25.2,20.2],[25.2,23.8],[20,23.8],[20,29.4],[31.25,29.4],[31.25,32.4]];
  // edges i: pts[i]->pts[i+1]; at x = -6 the crossbar top, its +y end and the +y underside stay sharp (bridge joins there)
  fneg = [1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0];
  fpos = [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1];
  chamfered_prism_yz(prof,-6,6,0.3,fneg,fpos);
  box([5,7.6,3.0],[-3.5,34.95,29.4]);
  box([5,3.0,9.5],[-3.5,38.0,23.1]);
  box([18,1.6,3.0],[6,35.9,29.4]);
  prism_xy([[11.0,35.1+OV],[11.0,33.6],[12.5,33.6],[15.0,35.1],[15.0,35.1+OV]],29.4,32.4);   // pawl barb, OV into the tongue
  box([4,2.2,3],[13,37.4,29.4]);
  // v0.7.2 second grip and guide shoulders
  box([5,7.6,3],[-3.5,-34.95,29.4]);
  box([5,3,9.5],[-3.5,-38,23.1]);
  for(sy=[-1,1]) box([5,4.55,6.3+OV],[-3.5,sy*37.225,23.1]);   // guide shoulders, OV into the grip bridge
}

// ---------------------------------------------------------------- end cap and gates (production-v08), cap frame
module end_cap() {
  difference() {
    union() {
      box([3.2,56,38],[1.6,0,0]);
      // insert (floor + two side plates), 0.5 mm lead-in chamfer at its tip
      chamfered_prism_yz([[-24.4,3.6],[24.4,3.6],[24.4,25.2],[21.6,25.2],[21.6,6.4],[-21.6,6.4],[-21.6,25.2],[-24.4,25.2]],
                         3.2-OV,25.2,0.5,[0,0,0,0,0,0,0,0],[1,1,1,1,1,1,1,1]);
      for(sy=[-1,1]) {
        box([22,16,4],[11,sy*35,34]);
        prism_xz([[0,28.4],[0,34.1],[18,34.1]], sy*27.05-2.25, sy*27.05-2.25+4.5);
      }
    }
    for(sy=[-1,1]) { box([2,4.6,5],[12,sy*35,33.5]); for(x=[11,13]) cyl(2.3,5,[x,sy*35,33.5]); }
    box([3.6,14.6,31],[1.6,0,8]);
    for(sy=[-1,1]) box([1.4,2.0,21.8],[1.7,sy*8.2,17.2]);
  }
}
GATE_OUTLINE = [[.25,-7.05],[1.2,-7.05],[1.2,-8.85],[2.2,-8.85],[2.2,-7.05],[2.95,-7.05],
                [2.95,7.05],[2.2,7.05],[2.2,8.85],[1.2,8.85],[1.2,7.05],[.25,7.05]];
module gate_wire() prism_xy(GATE_OUTLINE,17.2,17.2+20.8);
module gate_blank() { gate_wire(); box([2.7,14.1,9.1],[1.6,0,8.2]); }

// ---------------------------------------------------------------- light lock ring, ring stop pin, bracket stop pin
module lock_ring() {
  difference() { cyl(22,4.4,[0,0,14.4]); cyl(13.5,4.6,[0,0,14.3]); }
  for(a=LUGS) sector(21.5,24.9,a-8,a+8,14.4,4.4);
}
module ring_stop_pin() {          // v0.6.1 recessed pin, holder frame
  intersection() {
    difference() {
      union() {
        box([5,4,19.6],[AX,AY,8.6]);
        box([9,4,3],[AX,AY,28.2]);
        for(sx=[-1,1]) prism_xz([[AX+sx*2.49,9.1],[AX+sx*3.1,10.0],[AX+sx*2.49,10.8]], AY-2, AY+2);  // 2.49: 0.01 into the leg
      }
      box([.8,4.4,14.5],[AX,AY,8.5]);
    }
    box([30,30,30],[AX,AY,-5.8]);
  }
  box([9,3.6,3+OV],[AX,AY-.2,24.2-OV]);   // handle, OV into the stem
}
module bracket_stop_pin() { cyl(1.5,7.4,[-17.8,-30,28.8]); cyl(3,2,[-17.8,-30,36]); }


// ---------------------------------------------------------------- cable-tidy clips (port of hue-cable-tidy kit.py)
// Use frame: x along the surface, y along the wire, z out of the surface (z = 0 on the surface).
module rrect2(lx,ly,r) offset(r=r) square([lx-2*r, ly-2*r], center=true);
CL_H = 2.8 + 1.4;  CL_L = 18;  CL_XMIN = -(5.0 + 18.0 + 1.4);  CL_TIP = 8.4 + 0.6 + (2.8 - 0.9);
// rounded rectangle outline (centre c, size lx x ly, corner radius r) as points, the fragments offset(r=) would use
function _rr_pts(c, lx, ly, r, round_right=true) = let(n=max(1, ceil(_frag(r)/4)), hx=lx/2-r, hy=ly/2-r)
  concat(
    round_right ? [for(i=[0:n]) c + [hx,-hy] + r*[cos(-90+90*i/n), sin(-90+90*i/n)]] : [c + [lx/2,-ly/2]],
    round_right ? [for(i=[0:n]) c + [hx, hy] + r*[cos(90*i/n), sin(90*i/n)]] : [c + [lx/2, ly/2]],
    [for(i=[0:n]) c + [-hx, hy] + r*[cos(90+90*i/n), sin(90+90*i/n)]],
    [for(i=[0:n]) c + [-hx,-hy] + r*[cos(180+90*i/n), sin(180+90*i/n)]]);
module clip_flat_use() {
  H = CL_H; L = CL_L;
  difference() {
    hull() {                                         // pad, 0.5 mm chamfer round the show face (outline is convex);
      prism_xy(_rr_pts([CL_XMIN/2,0], -CL_XMIN, L, 2.5, false), 0, H-0.5);         // channel-side corners square
      prism_xy(_rr_pts([CL_XMIN/2,0], -CL_XMIN-1, L-1, 2.0, false), H-EPS, H);
    }
    span(-5.0, 0.5, -9/2-0.8, 9/2+0.8, -1, H+1);       // arm pocket; the two ears left are the wire stop
    span(-5.0-18, -5.0, -L, L, -1, 0.8);               // tape groove
    cyl(3.8/2, 20, [-14, 0, -10]);                     // #6 screw hole
    hull() { cyl(1.9, EPS, [-14,0,H-1.9+0.005]); cyl(3.8, EPS, [-14,0,H-1.9+0.005+1.91-EPS]); }   // 90 deg countersink
  }
  intersection() {                                   // sprung arm with the barb, tip corners rounded in plan
    prism_xz([[-5.8,H],[CL_TIP,H],[CL_TIP,2.8],[8.4+0.6,0.9],[8.4,0.9],[8.4,2.8],[-4.2,2.8],[-5.0,2.0],[-5.8,2.0]], -4.5, 4.5);
    prism_xy(_rr_pts([(CL_TIP-11)/2,0], CL_TIP+11, 9, 2.0), -1, H+1);
  }
}
R_RI = 9.5/2; R_RO = 9.5/2 + 1.3; R_ZC = 2.4 - 0.1 + 9.5/2 + 1.3;
function _ring_pts(r, alip) = [for(i=[0:48]) let(a=alip+(180-alip)*i/48) [r*sin(a), R_ZC + r*cos(a)]];
function ring_profile() = let(
  alip = asin(5.2/2/R_RI), inner = _ring_pts(R_RI, alip), outer = _ring_pts(R_RO, alip),
  lip = inner[0], hin = [lip[0]+2.4, lip[1]+2.6], dl = norm([2.4,2.6]),
  hout = [hin[0] + 1.3*2.6/dl, hin[1] - 1.3*2.4/dl],
  right = concat([hin, lip], [for(i=[1:48]) inner[i]]),
  bore = concat(right, [for(i=[len(right)-2:-1:0]) [-right[i][0], right[i][1]]]),
  oo = concat([hout], [for(i=[1:47]) outer[i]]),
  back = concat([for(q=oo) [-q[0], q[1]]], [[-1.5, 2.2], [1.5, 2.2]], [for(i=[len(oo)-1:-1:0]) oo[i]]))
  concat(bore, back);
module clip_round_use() {
  L = 18; x0 = -7.5; x1 = 18.5;
  difference() {
    union() {
      difference() {
        span(x0, x1, -L/2, L/2, 0, 2.4);
        // 45 deg corner: kit.py cuts both corners, but its -y polygon is clockwise, so build123d extruded it away from
        // the pad and the printed clip (the oracle) only has the +y corner cut. Reproduce what was printed.
        for(sy=[1]) prism_xy([[x1+0.01, sy*(L/2+0.01)], [x1-3, sy*(L/2+0.01)], [x1+0.01, sy*(L/2-3)]], -1, 2.4+1);
      }
      prism_xz(ring_profile(), -L/2, L/2);
    }
    prism_xy(concat(       // teardrop screw hole, apex toward +y (print up)
      [for(i=[0:40]) let(a=135+270*i/40) [13 + 1.9*cos(a), 1.9*sin(a)]], [[13, 1.9*sqrt(2)]]), -1, 2.4+1);
  }
}
module clip_flat() translate([0,0,CL_H]) rot90([180,0,0]) clip_flat_use();   // show face down
module clip_round() translate([0,0,9]) rot90([90,0,0]) clip_round_use();      // on its end

// ---------------------------------------------------------------- stash box base (port of hue-cable-tidy kit.py base())
// As installed: kit.py's base() equals the base on the as-printed plate (hue-cable-tidy out-v2/ref/asprinted_compare.json,
// surface deviation < 1e-6 mm). Use frame = print pose: back plate on the bed (z = 0), x along the beam, y up.
// The lid is not part of this file yet (lid v2 is being fit-checked).
SB_LI = 128; SB_HI = 2*(12+9+1)+19;  SB_LB = SB_LI + 4; SB_HB = SB_HI + 4;   // inside 128 x 63, outside 132 x 67
SB_RIM = 9.4; SB_TB = 1.6; SB_TW = 2.0; SB_RB = 7.9 - 1.6 - 0.3;             // rim, back plate, wall, corner radius 6
SB_HYC = SB_HI/2 - 1 - 21; SB_HXC = SB_LI/2 - 1 - 21;                       // hook centres (+-42, 9.5)
SB_SLOT_Y = -SB_HI/2 + 1 + 0.3 + 18/2;                                       // end slots (connector shelf line)
// revolve a closed (r, z) profile about the z axis through c, from angle a0 to a1 (deg, exact at multiples of 90)
module _revolve(prof, a0, a1, c) {
  m = len(prof); n = ceil(_frag(max([for(q=prof) q[0]])) * (a1-a0)/360);
  V = [for(k=[0:n], q=prof) let(a=a0+(a1-a0)*k/n) [c[0] + q[0]*cos(a), c[1] + q[0]*sin(a), q[1]]];
  sides = [for(k=[0:n-1], j=[0:m-1]) let(j1=(j+1)%m) [k*m+j, k*m+j1, (k+1)*m+j1, (k+1)*m+j]];   // profile counter-clockwise in (r, z)
  polyhedron(V, concat([[for(j=[m-1:-1:0]) j]], [[for(j=[0:m-1]) n*m+j]], sides), convexity=4);
}
// half-round hook open toward the box centre (r 10..12, 45 deg lip to r 14 above the 4th wire tier)
module sb_hook(sd) let(z0=SB_TB-0.2, zl=SB_TB+0.4+4*8.4, zt=40-1.8-0.2)
  _revolve([[10,z0],[12,z0],[12,zl],[14,zl+2],[14,zt],[10,zt]], sd>0 ? -90 : 90, sd>0 ? 90 : 270, [sd*SB_HXC, SB_HYC]);
module box_base() {
  span_x = 15 + 1.5;
  difference() {
    union() {
      difference() {
        union() {
          difference() {
            union() {
              difference() {
                prism_xy(_rr_pts([0,0], SB_LB, SB_HB, SB_RB), 0, SB_RIM);
                prism_xy(_rr_pts([0,0], SB_LI, SB_HI, SB_RB-SB_TW), SB_TB, SB_RIM+1);
              }
              for(sg=[1,-1]) let(Y=function(u) sg*SB_HB/2 + sg*u)     // inner rib behind the snap recess
                prism_yz([[Y(-SB_TW-1),SB_TB-0.1],[Y(-SB_TW+0.1),SB_TB-0.1],[Y(-SB_TW+0.1),SB_RIM],[Y(-SB_TW-1),SB_RIM]], -span_x, span_x);
            }
            for(sg=[1,-1]) let(Y=function(u) sg*SB_HB/2 + sg*u)       // 1 mm recess under the lid ridge
              prism_yz([[Y(-1),3],[Y(1),3],[Y(1),SB_RIM+1],[Y(-1),SB_RIM+1]], -span_x, span_x);
          }
          for(sg=[1,-1]) let(Y=function(u) sg*SB_HB/2 + sg*u)         // snap ridge: 45 deg underside, crest, lead-in
            prism_yz([[Y(-1.1),6.9],[Y(0.2),8.2],[Y(0.2),8.4],[Y(-0.8),SB_RIM],[Y(-1.1),SB_RIM]], -span_x, span_x);
        }
        for(sx=[1,-1]) span(sx*(SB_LI/2-0.5), sx*(SB_LB/2+1), SB_SLOT_Y-5, SB_SLOT_Y+5, SB_TB, SB_RIM+1);   // end slots
        for(sx=[1,-1]) span(sx*44-1.5, sx*44+1.5, -SB_HB/2-1, -SB_HI/2+0.5, SB_TB, SB_RIM+1);           // drain notches
      }
      sb_hook(-1); sb_hook(1);
      for(sx=[1,-1]) cyl(6, 3.8-SB_TB+0.1, [sx*22, SB_HYC, SB_TB-0.1]);                              // screw bosses
    }
    for(sx=[1,-1]) {                                                    // #6 screw holes, 90 deg countersinks
      cyl(1.9, 20, [sx*22, SB_HYC, -10]);
      hull() { cyl(1.9, EPS, [sx*22, SB_HYC, 1.9]); cyl(3.8, EPS, [sx*22, SB_HYC, 3.81-EPS]); }
    }
  }
}

// ---------------------------------------------------------------- run planner (port of production-v08 plan_sections.py)
UNIT = length_unit=="in" ? 25.4 : 1;
RUN = run_length*UNIT; SPACING = light_spacing*UNIT; LMARG = light_margin_min*UNIT;
BSMAX = bracket_spacing_max*UNIT; BEND = bracket_end_max*UNIT;
FIRST_LIGHT = first_light_offset*UNIT;
// Unit conversion may put an exact boundary a few floating-point ULPs below
// its decimal-mm value (12 * 25.4 versus 304.8). This is numeric tolerance,
// not additional mechanical clearance.
CAP_OFF = 3.2 + 0.4;                 // cap face to the first / last piece end
END_RULE = CAP_OFF + 53.6;           // light / bracket centre to a run end (cap insert + feature window)
SPACING_MIN = 304.8; SPACING_MAX = 533.4; STRING_PITCH = 569;   // 12 in, 21 in; 22.4 in factory pitch
GRID = 50.8; PREF = 203.2;           // joint station grid and preferred piece length (2 in, 8 in)
BED_LONG = max(bed_x, bed_y); BED_SHORT = min(bed_x, bed_y);
LIMIT = min(240, BED_LONG - 16);     // printed length = L + 11 (tongues) + 0.2 (rim band) <= bed - 2 x 2.4
function _r4(v) = round(v*1e4)/1e4;
function _r6(v) = round(v*1e6)/1e6;
function _fmt(v, d=1) = str(round(v*pow(10,d))/pow(10,d));
function _fin(v) = _fmt(v/25.4, 2);

// lights: as many as fit at SPACING with >= LMARG at each end, centred (LIGHTS0). The planner may shift the whole
// set (LIGHTS) by up to the spare margin if the centred set has no valid layout (small beds, dense brackets).
N_LIGHTS = floor((RUN - LMARG - (light_placement=="fixed" ? FIRST_LIGHT : LMARG))/SPACING + 1e-9) + 1;
LIGHT_M0 = light_placement=="fixed" ? FIRST_LIGHT : (RUN - (N_LIGHTS-1)*SPACING)/2;
LIGHTS0 = [for(i=[0:1:N_LIGHTS-1]) LIGHT_M0 + i*SPACING];

// joints: the production DP (fewest pieces, then lengths closest to 8 in) over 2 in stations that keep >= 50.8 mm
// from every light and bracket and leave >= 88.9 mm of pin approach on one side
function _mind(x, fs) = min([for(f=fs) abs(x-f)]);
function _pin(x, fs) = let(l=[for(f=fs) if(f<x) x-f], r=[for(f=fs) if(f>=x) f-x],
  dl = len(l)>0 ? min(l) : 1e6, dr = len(r)>0 ? min(r) : 1e6) [dl >= dr-0.001 ? "left" : "right", max(dl, dr)];
function _cands(fs, g=GRID) = [for(j=[1:1:floor(RUN/g)]) let(x=j*g)
  if(x>=50.8-1e-6 && x<=RUN-50.8+1e-6 && _mind(x,fs)>=50.79 && _pin(x,fs)[1]>=88.9) x];
function _better(a,b) = a[0]<b[0] || (a[0]==b[0] && a[1]<b[1]);
function _lexmin(c, i=1, m=undef) = let(m0 = (m==undef) ? c[0] : m)
  i>=len(c) ? m0 : _lexmin(c, i+1, _better(c[i], m0) ? c[i] : m0);
function _best_k(xs, j, best, lo=0) = let(c=[for(k=[lo:1:j-1]) let(g=xs[j]-xs[k]-SEAM)
  // End sections have only one half-seam, not a full seam. Check their actual
  // length; preserve the installed planner's tie-break cost for valid layouts.
  if(g>30 && g+(k==0?SEAM/2:0)+(j==len(xs)-1?SEAM/2:0)<=LIMIT+1e-9 && best[k][0]<1e9) [best[k][0]+1, best[k][1]+_r4(pow(g-PREF,2)), k]])
  len(c)==0 ? [1e9, 1e99, -1] : _lexmin(c);
// lo: first k with xs[j] - xs[k] - SEAM <= LIMIT (window pointer, keeps the DP linear on fine grids)
function _lo(xs, j, lo) = (lo < j && xs[j]-xs[lo]-SEAM > LIMIT+1e-9) ? _lo(xs, j, lo+1) : lo;
function _dp(xs, j=1, best=[[0,0,-1]], lo=0) = j>=len(xs) ? best :
  let(l=_lo(xs, j, lo)) _dp(xs, j+1, concat(best, [_best_k(xs, j, best, l)]), l);
function _back(best, j, acc=[]) = j<=0 ? acc : _back(best, best[j][2], concat([j], acc));
function _joints_g(fs, g) = let(xs=concat([CAP_OFF], _cands(fs, g), [RUN-CAP_OFF]), b=_dp(xs), n=len(xs)-1)
  b[n][0] >= 1e9 ? undef : [for(j=_back(b, n)) if(j!=n) xs[j]];
// Dylan's 2 in station grid first; 1 in and 1/2 in only if the coarser grid has no layout (dense lights on a small
// bed). The grid is only a measuring convenience.
function _joints(fs) = let(a=_joints_g(fs, GRID)) a != undef ? a :
  let(b=_joints_g(fs, GRID/2)) b != undef ? b : _joints_g(fs, GRID/4);

// brackets and the plan. Strategies, in order, for each light set (centred first, then shifted by 6, 12, ... mm):
//  1 Dylan's: brackets evenly spaced at the largest spacing <= BSMAX with ends <= BEND (the whole set may shift by up
//    to 60 mm), joints on the 2 in grid;  2 brackets midway between lights (greedy, farthest within BSMAX), joints on
//    2 / 1 / 0.5 in grids;  3 strategy 1 again with the finer joint grids.
// A bracket and a light either share a piece (62 <= gap <= LIMIT - 101.2) or have a joint between them, which needs
// 50.8 mm to one and 88.9 mm (pin approach) to the other (gap >= 139.7).
function _br(nsp, s, d=0) = let(m=(RUN-nsp*s)/2+d) [for(i=[0:nsp]) m+i*s];
function _bad_gap(d) = d < 62-1e-6 || (d > LIMIT-101.2+1e-6 && d < 139.7-1e-6);
function _conf(bs, ls) = len([for(b=bs, l=ls) if(_bad_gap(abs(b-l))) 1]) > 0;
function _ends_ok(bs) = bs[0] >= END_RULE-1e-6 && bs[0] <= BEND+1e-6 && bs[len(bs)-1] <= RUN-END_RULE+1e-6 && bs[len(bs)-1] >= RUN-BEND-1e-6;
function _delta(k, st=6) = (k%2==0 ? 1 : -1)*ceil(k/2)*st;      // 0, -6, +6, -12, ...
NSP0 = max(1, ceil((RUN-2*BEND)/BSMAX - 1e-9));
function _even(ls, fine, nsp=NSP0, k=0) = nsp > NSP0+6 ? undef :
  let(smax=min(BSMAX, (RUN-2*END_RULE)/nsp), smin=(RUN-2*BEND)/nsp, s=smax-(fine?8:2)*k)
  (smax < smin-1e-9 || s < smin-1e-9) ? _even(ls, fine, nsp+1, 0) :
  let(found=[for(dk=[0:1:20]) let(bs=_br(nsp, s, _delta(dk))) if(_ends_ok(bs) && !_conf(bs, ls)) bs],
      js = len(found)==0 ? undef : fine ? _joints(concat(ls, found[0])) : _joints_g(concat(ls, found[0]), GRID))
  js != undef ? [found[0], js] : _even(ls, fine, nsp, k+1);
function _qsort1(v) = [for(e=_qsort([for(x=v) [x]])) e[0]];
// candidate bracket positions: light midpoints, every 2 mm in the end zones, and the gap-rule edges next to each light
// (end zones only; the gap-rule edges get 1/2 in of slack so a joint grid point fits, and the shared-piece band is
// used only when it is >= 10 mm wide)
function _in_end(x) = (x >= END_RULE-1e-6 && x <= BEND+1e-6) || (x >= RUN-BEND-1e-6 && x <= RUN-END_RULE+1e-6);
function _mid_c(ls) = let(n=len(ls), band=LIMIT-101.2-62,
  offs = concat([-152.4, 152.4], band >= 10 ? [-62-band/2, 62+band/2] : []),
  ends = concat([for(x=[END_RULE:2:min(BEND, RUN/2)]) x], [for(x=[RUN-min(BEND, RUN/2):2:RUN-END_RULE]) x],
                [for(l=ls, o=offs) if(_in_end(l+o)) l+o]))
  [for(c=_qsort1(concat([for(i=[0:1:n-2]) (ls[i]+ls[i+1])/2], ends))) if(c >= END_RULE-1e-6 && c <= RUN-END_RULE+1e-6 && !_conf([c], ls)) c];
function _greedy(C, prev, acc) = let(nxt=[for(c=C) if(c > prev+62 && c <= prev+BSMAX+1e-6) c])
  prev >= RUN-BEND-1e-6 ? acc : len(nxt)==0 ? undef : _greedy(C, max(nxt), concat(acc, [max(nxt)]));
function _mid(ls) = let(C=_mid_c(ls), first=[for(c=C) if(c <= BEND+1e-6) c],
  bs = len(first)==0 ? undef : _greedy(C, max(first), [max(first)]),
  ok = bs != undef && bs[len(bs)-1] <= RUN-END_RULE+1e-6, js = ok ? _joints(concat(ls, bs)) : undef)
  js != undef ? [bs, js] : undef;
// A compact decimal CSV parser keeps measured positions usable in browser
// Customizers without unsupported array widgets or executable user expressions.
function _csv_tokens(s,i=0,t="",a=[]) = i>=len(s) ? concat(a,[t]) :
  s[i]=="," ? _csv_tokens(s,i+1,"",concat(a,[t])) : s[i]==" " ? _csv_tokens(s,i+1,t,a) : _csv_tokens(s,i+1,str(t,s[i]),a);
function _decimal(s,i=0,v=0,d=0,dot=false) = assert(len(s)>0,"empty bracket position") i>=len(s) ? v/pow(10,d) :
  s[i]=="." && !dot ? _decimal(s,i+1,v,d,true) :
  assert(ord(s[i])>=48 && ord(s[i])<=57,"bracket positions must be plain nonnegative decimal millimetres")
  _decimal(s,i+1,10*v+ord(s[i])-48,d+(dot?1:0),dot);
MANUAL_BRACKETS = bracket_centres_mm=="" ? [] : [for(t=_csv_tokens(bracket_centres_mm)) _decimal(t)];
function _manual(ls) = let(bs=MANUAL_BRACKETS,valid=len(bs)>=2 && _ends_ok(bs) && !_conf(bs,ls) &&
  len([for(i=[1:1:len(bs)-1]) if(bs[i]-bs[i-1]<62 || bs[i]-bs[i-1]>BSMAX+1e-6) 1])==0,
  a=valid?_joints(concat(ls,bs)):undef, b=a==undef && valid?_joints_x(concat(ls,bs)):a)
  b==undef ? undef : [bs,b];
function _plan_for(ls, full) = len(MANUAL_BRACKETS)>0 ? _manual(ls) :
  let(a=_even(ls, false)) a != undef ? a : let(b=_mid(ls)) b != undef ? b : full ? _even(ls, true) : undef;
// light shifts that keep both margins >= LMARG (and the 57.2 mm cap rule): 0, -6, +6, ... up to the spare margin.
// Last resort: one or two lights fewer (bigger end margins), when the ends cannot hold a bracket within
// bracket_end_max on short pieces (small beds); the bill of materials says so.
function _lights(n) = let(m=light_placement=="fixed"?FIRST_LIGHT:(RUN-(n-1)*SPACING)/2) [for(i=[0:1:n-1]) m+i*SPACING];
// Tight fallback (phase 3), tried only when strategies 1-3 find no layout for this light count at any shift, before a
// light is dropped. Same rules (bracket spacing, end limit, joint clearances, pin approach, piece length), but
//  * joints may also sit exactly at the clearance limits (feature +/- 50.8 and +/- 88.9) besides the 2 in stations, and
//  * bracket candidates always include light +/- the centre of the shared-piece band (62.4 mm on a 180 bed), and every
//    end-zone candidate is tried as the first bracket (largest first), not only the farthest one.
// On a 164 mm piece a light and a bracket share a piece only if both joints sit within 0.4 mm of their limits, which
// no station grid hits; that is why small beds dropped a light.
// End pieces in this fallback are >= END_MIN_X = 47 mm long: the cap insert reaches 21.2 mm into the piece and the
// joint block is 14 mm long, so >= 11.8 mm stay clear between them (the strict planner already makes 47.0 mm end
// pieces). A 35.4 mm end piece, which the fallback found without this limit, would leave only 0.2 mm.
END_MIN_X = 47;
function _cands_x(fs) = let(g=[for(j=[1:1:floor(RUN/GRID)]) j*GRID], e=[for(f=fs, o=[-88.9,-50.8,50.8,88.9]) _r6(f+o)],
  lo=CAP_OFF+SEAM/2+END_MIN_X)
  [for(x=_dedupe1(_qsort1(concat(g, e)))) if(x>=lo-1e-6 && x<=RUN-lo+1e-6 && _mind(x,fs)>=50.79 && _pin(x,fs)[1]>=88.9) x];
function _dedupe1(v) = [for(i=[0:1:len(v)-1]) if(i==0 || v[i]-v[i-1] > 1e-6) v[i]];
function _joints_x(fs) = let(xs=concat([CAP_OFF], _cands_x(fs), [RUN-CAP_OFF]), b=_dp(xs), n=len(xs)-1)
  b[n][0] >= 1e9 ? undef : [for(j=_back(b, n)) if(j!=n) xs[j]];
function _tight_c(ls) = let(sh=62+(LIMIT-101.2-62)/2)
  [for(c=_dedupe1(_qsort1(concat(_mid_c(ls), [for(l=ls, o=[-sh, sh]) l+o])))) if(c >= END_RULE-1e-6 && c <= RUN-END_RULE+1e-6 && !_conf([c], ls)) c];
// two candidate sets: all of them, then shared-band candidates in the end zones only (interior brackets midway
// between lights or at the gap-rule edges, which leaves the joints more room)
function _tight(ls) = let(C=_tight_c(ls), sh=62+(LIMIT-101.2-62)/2,
  C2=[for(c=C) if(_in_end(c) || len([for(l=ls) if(abs(abs(c-l)-sh) < 1e-6) 1])==0) c],
  a=_tight_try(ls, C)) a != undef ? a : _tight_try(ls, C2);
function _tight_try(ls, C, i=undef) = let(first=[for(c=C) if(c <= BEND+1e-6) c], ii = i==undef ? len(first)-1 : i)
  ii < 0 ? undef :
  let(bs=_greedy(C, first[ii], [first[ii]]), ok = bs != undef && bs[len(bs)-1] <= RUN-END_RULE+1e-6,
      js = ok ? _joints_x(concat(ls, bs)) : undef)
  js != undef ? [bs, js] : _tight_try(ls, C, ii-1);
function _plan(n=N_LIGHTS, k=0, tight=false) = light_placement=="fixed" ?
  let(ls=_lights(n),a=_plan_for(ls,true),p=a==undef && len(MANUAL_BRACKETS)==0?_tight(ls):a) p==undef?undef:[p[0],p[1],ls] :
  n < max(1, N_LIGHTS-2) ? undef :
  let(l0=_lights(n), slack=l0[0]-max(LMARG, END_RULE), d=_delta(k, 12.7))
  abs(d) > slack+1e-6 ? (tight ? _plan(n-1, 0) : _plan(n, 0, true)) :
  let(ls=[for(x=l0) x+d], p = len(MANUAL_BRACKETS)>0 ? _manual(ls) : tight ? _tight(ls) : _plan_for(ls, k==0))
  p != undef ? [p[0], p[1], ls] : _plan(n, k+1, tight);

PLAN_OK_INPUT = RUN>=304.8 && RUN<=15240 && bed_x>=180 && bed_y>=180 && SPACING >= SPACING_MIN-1e-6 && SPACING <= SPACING_MAX+1e-6 && N_LIGHTS >= 1 && LIGHT_M0 >= END_RULE-1e-6;
PLAN = PLAN_OK_INPUT ? _plan() : undef;
LIGHTS = PLAN==undef ? LIGHTS0 : PLAN[2];
N_LIGHTS_FIT = N_LIGHTS;
N_LIT = len(LIGHTS);
LIGHT_M = LIGHTS[0];
BRACKETS = PLAN==undef ? [] : PLAN[0];
JOINTS = PLAN==undef ? [] : PLAN[1];
FEATS = concat(LIGHTS, BRACKETS);
BREAKS = concat([CAP_OFF], JOINTS, [RUN-CAP_OFF]);
NP = PLAN==undef ? 0 : len(BREAKS)-1;
// section: [start, stop, length, first, last, light offsets, mount offsets]
function _sec(k) = let(a=BREAKS[k], b=BREAKS[k+1], st=a+(k>0?SEAM/2:0), sp=b-(k<NP-1?SEAM/2:0), c=(st+sp)/2)
  [st, sp, sp-st, k==0, k==NP-1, [for(x=LIGHTS) if(x>st && x<sp) x-c], [for(x=BRACKETS) if(x>st && x<sp) x-c]];
SECTIONS = PLAN==undef ? [] : [for(k=[0:1:NP-1]) _sec(k)];
SIGS = [for(q=SECTIONS) [_r6(q[2]), q[3], q[4], [for(x=q[5]) _r6(x)], [for(x=q[6]) _r6(x)]]];
FIRST_OF = [for(i=[0:1:len(SIGS)-1]) [for(j=[0:i]) if(SIGS[j]==SIGS[i]) j][0]];
TYPE_FIRSTS = [for(i=[0:1:len(SIGS)-1]) if(FIRST_OF[i]==i) i];
TYPE_OF = [for(i=[0:1:len(SIGS)-1]) [for(t=[0:len(TYPE_FIRSTS)-1]) if(TYPE_FIRSTS[t]==FIRST_OF[i]) t][0]];
PIN_SIDE = [for(x=JOINTS) _pin(x, FEATS)[0]];
N_JOINTS = len(JOINTS);
function _tname(t) = str("T", t+1 < 10 ? "0" : "", t+1);
function printed_len(q) = q[2] + (q[3] ? 0 : 11) + (q[4] ? 0 : 0.2);
function piece_x_min(q) = q[3] ? -q[2]/2 : -q[2]/2 - 11;

// ---------------------------------------------------------------- bill of materials
function _spare(n) = n==0 || spare_percent==0 ? 0 : max(2, ceil(n*spare_percent/100));
N_BRK = len(BRACKETS);
// [part, print count, spares, approx grams each (Dylan's X2D PETG slices / volume estimate)]
HW = [["bracket", N_BRK, 0, 18.0], ["lever", N_BRK, 0, 2.5], ["bracket_stop_pin", N_BRK, _spare(N_BRK), 0.15],
      ["lock_ring", N_LIT, 0, 4.8], ["ring_stop_pin", N_LIT, _spare(N_LIT), 0.45],
      ["splice_bar", 2*N_JOINTS, _spare(2*N_JOINTS), 1.2], ["jb6_pin", 2*N_JOINTS, _spare(2*N_JOINTS), 0.85],
      ["end_cap", 2, 0, 11.3], ["gate_wire", (start_gate=="wire"?1:0)+(end_gate=="wire"?1:0), 0, 1.1],
      ["gate_blank", (start_gate=="blank"?1:0)+(end_gate=="blank"?1:0), 0, 1.5],
      ["clip_flat", clips_flat, 0, 1.6], ["clip_round", clips_round, 0, 1.4]];
// track piece grams fitted to Dylan's sliced plates (0.28 mm, 2 walls, PETG): 0.2165 g/mm, 3.35 g per joint end,
// +6.6 g per light holder, -1.5 g per bracket receiver (full walls replace the lightened ones)
function piece_g(q) = 0.2165*q[2] + 3.35*((q[3]?0:1)+(q[4]?0:1)) + 6.6*len(q[5]) - 1.5*len(q[6])
  + q[2]*(49.6*(FACE_SKIN-1.6)+2*24.8*(SIDE_WALL-1.8))*0.00124;
TRACK_G = PLAN==undef ? 0 : sum([for(q=SECTIONS) piece_g(q)]);
HW_G = sum([for(h=HW) (h[1]+h[2])*h[3]]);

// ---------------------------------------------------------------- plates
EDGE = 2.4; GAP = 4; ROW_GAP = 3;
ROWS_PER_PLATE = floor((BED_SHORT - 2*EDGE + ROW_GAP)/(W + ROW_GAP));
ROW_CAP = BED_LONG - 2*EDGE;
// first-fit decreasing of pieces (by printed length) into rows of the long bed axis
function _desc(ids) = [for(e=_qsort([for(i=ids) [-printed_len(SECTIONS[i]) + i*1e-9, i]])) e[1]];
function _ffd(ids, rows=[], k=0) = k>=len(ids) ? rows : let(i=ids[k], l=printed_len(SECTIONS[i]),
  fit=[for(r=[0:1:len(rows)-1]) if(rows[r][0] + GAP + l <= ROW_CAP + 1e-6) r])
  len(fit)>0 ? _ffd(ids, [for(r=[0:len(rows)-1]) r==fit[0] ? [rows[r][0]+GAP+l, concat(rows[r][1],[i])] : rows[r]], k+1)
             : _ffd(ids, concat(rows, [[l, [i]]]), k+1);
function _chunk(v, n) = [for(i=[0:n:len(v)-1]) [for(j=[i:1:min(i+n,len(v))-1]) v[j]]];
function _rows(ids) = [for(r=_ffd(_desc(ids))) r[1]];
SUPP = [for(i=[0:1:NP-1]) if(len(SECTIONS[i][5])+len(SECTIONS[i][6])>0) i];
PLAIN = [for(i=[0:1:NP-1]) if(len(SECTIONS[i][5])+len(SECTIONS[i][6])==0) i];
TRACK_PLATES = PLAN==undef ? [] : group_supported_pieces
  ? concat(len(SUPP)>0 ? _chunk(_rows(SUPP), ROWS_PER_PLATE) : [], len(PLAIN)>0 ? _chunk(_rows(PLAIN), ROWS_PER_PLATE) : [])
  : _chunk(_rows([for(i=[0:1:NP-1]) i]), ROWS_PER_PLATE);
// print-orientation bounding boxes [min, size] of the hardware parts (from the renders; see tools/hw_bbox.py)
HW_BB = [
  ["bracket", [18.0, -34.5, -30.0], [20.0, 69.0, 60.0]],
  ["lever", [-32.6, -39.5, -6.0], [12.4, 79.0, 21.0]],
  ["bracket_stop_pin", [-20.8, 27.0, -38.0], [6.0, 6.0, 9.2]],
  ["lock_ring", [-23.81199, -23.81199, 14.4], [47.62398, 47.62398, 4.4]],
  ["ring_stop_pin", [-15.14998, -27.2, 20.83896], [9.0, 18.6, 4.0]],
  ["splice_bar", [-13.9, -17.64142, 18.7], [28.2, 15.84142, 3.0]],
  ["jb6_pin", [-17.65, 15.7, 17.2], [33.95, 9.0, 7.0]],
  ["end_cap", [-38.0, -43.0, 0.0], [38.0, 86.0, 25.2]],
  ["gate_wire", [0.25, -8.85, 17.2], [2.7, 17.7, 20.8]],
  ["gate_blank", [0.25, -8.85, 8.2], [2.7, 17.7, 29.8]],
  ["clip_flat", [-24.4, -9.0, -0.0], [35.3, 18.0, 4.2]],
  ["clip_round", [-7.5, -14.92524, 0.0], [26.0, 14.92524, 18.0]]];
function hw_bb(n) = [for(e=HW_BB) if(e[0]==n) e][0];
function needs_tree(n) = n=="bracket" || n=="lever";
function hw_halo(n) = needs_tree(n) ? 10 : 0;
// shelf packing of the hardware (print counts + spares) over plates of bed_x by bed_y
HW_ITEMS = [for(h=HW) for(i=[0:1:h[1]+h[2]-1]) if(h[1]+h[2]>0) h[0]];
function _shelf(items, k=0, p=0, x=0, y=0, sh=0, acc=[]) = k>=len(items) ? acc :
  let(b=hw_bb(items[k]), halo=hw_halo(items[k]), fx=b[2][0]+2*halo, fy=b[2][1]+2*halo, WX=bed_x-2*EDGE, WY=bed_y-2*EDGE,
      newrow = x>0 && x+fx > WX, nx = newrow ? 0 : x, ny = newrow ? y+sh+GAP : y, nsh = newrow ? 0 : sh,
      newplate = ny+fy > WY, px = newplate ? 0 : nx, py = newplate ? 0 : ny, pp = newplate ? p+1 : p, psh = newplate ? 0 : nsh)
  _shelf(items, k+1, pp, px+fx+GAP, py, max(psh, fy), concat(acc, [[pp, items[k], px+halo, py+halo]]));
// Brackets/levers get a support halo and their own plate group. This prevents
// organic tree toolpaths from crossing neighboring small-part models.
HW_SUPPORTED = _shelf([for(n=HW_ITEMS) if(needs_tree(n)) n]);
HW_SUPPORT_PLATES = len(HW_SUPPORTED)==0 ? 0 : HW_SUPPORTED[len(HW_SUPPORTED)-1][0]+1;
HW_PLAIN = _shelf([for(n=HW_ITEMS) if(!needs_tree(n)) n]);
HW_PLACED = concat(HW_SUPPORTED,[for(e=HW_PLAIN) [e[0]+HW_SUPPORT_PLATES,e[1],e[2],e[3]]]);
N_HW_PLATES = len(HW_PLACED)==0 ? 0 : HW_PLACED[len(HW_PLACED)-1][0]+1;
N_TRACK_PLATES = len(TRACK_PLATES);
N_PLATES = N_TRACK_PLATES + N_HW_PLATES;
function plate_pieces(n) = [for(r=TRACK_PLATES[n]) each r];

// ---------------------------------------------------------------- echo plan + BOM (console) and the BOM card
function _list(v) = len(v)==0 ? "-" : str(v[0], len(v)>1 ? str(", ", _list([for(i=[1:len(v)-1]) v[i]])) : "");
BOM_LINES = PLAN==undef ? ["NO VALID LAYOUT - see the console message"] : concat([
  str("Run ", _fin(RUN), " in (", _fmt(RUN), " mm). Compatible with Philips Hue Festavia permanent lights."),
  str("Lights: ", N_LIT, N_LIT < N_LIGHTS_FIT ? str(" (", N_LIGHTS_FIT-N_LIT, " fewer than fit, to leave room for the end brackets on this bed)") : "", " at ", _fin(SPACING), " in (", _fmt(SPACING), " mm), first at ", _fin(LIGHTS[0]), " in, last ", _fin(RUN-LIGHTS[N_LIT-1]), " in from the end."),
  str("  Spare cable per gap: ~", round(STRING_PITCH-SPACING), " mm (string pitch 22.4 in / 569 mm); it lies loose in the channel."),
  str("Brackets: ", N_BRK, ", at most ", _fin(max([for(i=[1:1:N_BRK-1]) BRACKETS[i]-BRACKETS[i-1]])), " in apart, first at ",
      _fin(BRACKETS[0]), " in, last ", _fin(RUN-BRACKETS[N_BRK-1]), " in from the end."),
  str("  Bracket centres from the run start (in): ", _list([for(b=BRACKETS) _fin(b)])),
  str("Track pieces: ", NP, " (", len(TYPE_FIRSTS), " types), joints: ", N_JOINTS, ", bed ", bed_x, " x ", bed_y, " mm, max piece ", _fmt(LIMIT), " mm."),
  str("Plates: ", N_PLATES, " (track 1-", N_TRACK_PLATES, ", hardware ", N_TRACK_PLATES+1, "-", N_PLATES, ")",
      single_nozzle ? ", track supports OFF; brackets/levers need supports. Remove track ribs." : ", supports needed on light/mount pieces and brackets/levers."),
  "Print (count + spares):"],
  [for(h=HW) if(h[1]+h[2]>0) str("  ", h[0], ": ", h[1], h[2]>0 ? str(" + ", h[2]) : "")],
  [str("Buy: ", 2*N_BRK + 4, " exterior screws for the soffit (2 per bracket, 2 per end cap; length to suit the backing)."),
   str("PETG material budget: ~", round(TRACK_G + HW_G), " g (conservative shell allowance; use your slicer for final mass)."),
   str("Shell: ", structure_profile, ", face ", FACE_SKIN, " mm, side ", SIDE_WALL, " mm. Not a load or wind rating."),
   "Pieces (number: type, length mm, light / bracket offset mm):"],
  [for(r=_chunk([for(i=[0:1:NP-1]) let(q=SECTIONS[i]) str(i+1, ":", _tname(TYPE_OF[i]), " ", _fmt(q[2]),
      len(q[5])>0 ? str(" L", _fmt(q[5][0])) : "", len(q[6])>0 ? str(" B", _fmt(q[6][0])) : "")], 4)) str("  ", _list(r))],
  [str("Pins: pushed in from the ", "piece on the side listed per joint: ", _list([for(j=[0:1:N_JOINTS-1]) str(j+1, PIN_SIDE[j]=="left"?"L":"R")]))]);
module bom_card() {          // one solid: text raised 0.6 mm, overlapping the 1 mm card by 0.4 mm
  n = len(BOM_LINES);
  span(0, 10 + 2.3*max([for(l=BOM_LINES) len(l)]), 0, 8 + 6.5*n, 0, 1.0);   // wide enough for the longest line
  translate([0,0,0.6]) linear_extrude(1.0) for(i=[0:n-1]) translate([4, 4 + 6.5*(n-1-i)]) text(BOM_LINES[i], size=3.6, font="Liberation Sans");
}

// ---------------------------------------------------------------- single-nozzle test plate (2 short sections)
// The two 60 mm windows that carry every supported feature: a light holder (v2 fill, tab ribs, stop fill) and a
// bracket receiver (gusset, slot-roof combs). Print with supports OFF, snap the ribs out, then try a ring and a lever.
module sn_light_section() { lc6_holder(true); holder_ribs(); }
module sn_mount_section() { mount_receiver(); receiver_gusset(); receiver_ribs(); }
module test_plate_single_nozzle() {
  translate([EDGE+30, EDGE+28, 0]) sn_light_section();
  translate([EDGE+30, EDGE+28+W+8, 0]) sn_mount_section();
}

// Two 80 mm reference-interface halves, two splice bars and two pins. Fully fits
// a 180 mm bed. No support interface, glue or external hardware required.
module joint_test_plate() {
  translate([EDGE+40,EDGE+28,0]) track_piece(80,[],[],"cap","socket",joint_fit,"",false);
  translate([EDGE+51,EDGE+88,0]) track_piece(80,[],[],"tongue","cap",joint_fit,"",false);
  for(i=[0:1]) {
    let(b=hw_bb("splice_bar")) translate([EDGE+34*i-b[1][0],EDGE+120-b[1][1],-b[1][2]]) hw_part("splice_bar");
    let(b=hw_bb("jb6_pin")) translate([EDGE+40*i-b[1][0],EDGE+142-b[1][1],-b[1][2]]) hw_part("jb6_pin");
  }
}

// ---------------------------------------------------------------- dispatch
SN = single_nozzle;
module plan_piece(i) let(q=SECTIONS[i])
  track_piece(q[2], q[5], q[6], q[3]?"cap":"tongue", q[4]?"cap":"socket", joint_fit, engrave_numbers ? str(i+1) : "", SN);
module hw_part(n) {
  if(n=="bracket") rot90([0,90,0]) bracket();
  else if(n=="lever") rot90([0,-90,0]) lever();
  else if(n=="splice_bar") rot90([90,0,0]) splice_bar();
  else if(n=="jb6_pin") jb6_pin();
  else if(n=="end_cap") rot90([0,-90,0]) end_cap();
  else if(n=="gate_wire") gate_wire();
  else if(n=="gate_blank") gate_blank();
  else if(n=="lock_ring") lock_ring();
  else if(n=="ring_stop_pin") rot90([90,0,0]) ring_stop_pin();
  else if(n=="bracket_stop_pin") rot90([180,0,0]) bracket_stop_pin();
  else if(n=="clip_flat") clip_flat();
  else if(n=="clip_round") clip_round();
  else if(n=="box_base") box_base();
}
module plate(n) {
  assert(n>=1 && n<=N_PLATES, str("plate_number must be 1 to ", N_PLATES, " for this run"));
  // number of separate parts on this plate (tools/mesh_audit.py checks one body per part)
  echo(str("PLATE_PARTS ", n <= N_TRACK_PLATES ? len(plate_pieces(n-1)) : len([for(e=HW_PLACED) if(e[0]==n-1-N_TRACK_PLATES) 1])));
  if(n <= N_TRACK_PLATES) {
    along_x = bed_x >= bed_y;
    rows = TRACK_PLATES[n-1];
    for(r=[0:len(rows)-1]) for(k=[0:len(rows[r])-1]) let(i=rows[r][k],
        x0 = EDGE + sum([for(j=[0:1:k-1]) printed_len(SECTIONS[rows[r][j]]) + GAP]), y0 = EDGE + r*(W+ROW_GAP) + W/2)
      if(along_x) translate([x0 - piece_x_min(SECTIONS[i]), y0, 0]) plan_piece(i);
      else translate([y0, x0 - piece_x_min(SECTIONS[i]), 0]) rot90([0,0,90]) plan_piece(i);
  } else {
    for(e=HW_PLACED) if(e[0]==n-1-N_TRACK_PLATES) let(b=hw_bb(e[1]))
      translate([EDGE + e[2] - b[1][0], EDGE + e[3] - b[1][1], -b[1][2]]) hw_part(e[1]);
  }
}

module checked_inputs() {
    $fa = 4;
    $fs = 0.25;
    $ox = 0;
    assert(length_unit=="in" || length_unit=="mm", "length_unit must be in or mm");
    assert(bed_x>=180 && bed_x<=400 && bed_y>=180 && bed_y<=400, "bed dimensions must be 180 to 400 mm");
    assert(structure_profile=="reinforced" || structure_profile=="as_installed" || structure_profile=="custom", "unknown structure profile");
    assert(FACE_SKIN>=1.6 && FACE_SKIN<=3.2 && SIDE_WALL>=1.8 && SIDE_WALL<=3.2, "shell thickness is outside the supported range");
    assert(fit_profile=="A0" || fit_profile=="loose" || fit_profile=="tight", "unknown fit profile");
    assert(support_gap>=0.2 && support_gap<=0.5, "support gap must be 0.2 to 0.5 mm");
    assert(spare_percent>=0 && spare_percent<=50 && clips_flat>=0 && clips_flat<=40 && clips_round>=0 && clips_round<=40, "invalid spare or clip quantity");
    assert(light_placement=="auto" || light_placement=="fixed", "unknown light placement mode");
    assert(light_placement!="fixed" || FIRST_LIGHT>=max(LMARG,57.2)-1e-7, "fixed first light is inside the minimum end margin");
    assert(RUN>=304.8-1e-7 && RUN<=15240+1e-7, "run length must be 12 to 600 inches (304.8 to 15240 mm); plan longer installations as separate supported runs");
    assert(BSMAX>=203.2-1e-7 && BSMAX<=609.6+1e-7, "maximum bracket spacing must be 8 to 24 inches (203.2 to 609.6 mm)");
    assert(BEND>=57.2-1e-7 && BEND<=203.2+1e-7, "end bracket limit must be 57.2 to 203.2 mm (2.252 to 8 inches)");
    assert(LMARG>=57.2-1e-7, "minimum light end margin must be at least 57.2 mm (2.252 inches); check the selected units");
    children();
}

checked_inputs() if (output_model=="joint") translate([-52,-80,0]) joint_test_plate();
else if (output_model=="holder") translate([-EDGE-30,-EDGE-W-4,0]) test_plate_single_nozzle();
else track_piece(piece_length, has_light ? [(light_side=="left" ? -1 : 1)*light_offset] : [],
    has_mount ? [(mount_side=="left" ? -1 : 1)*mount_offset] : [],
    left_end, right_end, joint_fit, label_text, single_nozzle);
