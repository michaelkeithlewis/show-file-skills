# locate_clip.py <source.wav> <clip.wav>
# Find where a short clip sits inside a long source recording (FFT cross-correlation,
# coarse at 2 kHz then sample-accurate at 48 kHz) and report the gain between them.
# Use it to line up a re-bounce against a file you already have. Needs ffmpeg and numpy.
import subprocess, sys, numpy as np
def load(p, sr, ss=None, t=None):
    cmd=["ffmpeg","-v","error"]
    if ss is not None: cmd+=["-ss",f"{ss:.6f}"]
    if t is not None: cmd+=["-t",f"{t:.6f}"]
    cmd+=["-i",p,"-ac","1","-ar",str(sr),"-f","f32le","-"]
    return np.frombuffer(subprocess.run(cmd,capture_output=True).stdout,dtype=np.float32).astype(np.float64)
def xc(ref,x):
    n=len(ref)+len(x); N=1<<(n-1).bit_length()
    c=np.fft.irfft(np.fft.rfft(ref,N)*np.conj(np.fft.rfft(x,N)),N)
    return c,N
src,clip=sys.argv[1],sys.argv[2]
# coarse at 2k
SR=2000
ref=load(src,SR); x=load(clip,SR)
c,N=xc(ref,x)
c=c[:len(ref)]
# normalise by local energy of ref
cs=np.concatenate([[0],np.cumsum(ref**2)])
L=len(x); e=np.sqrt(np.maximum(cs[np.minimum(np.arange(len(ref))+L,len(ref))]-cs[:len(ref)],1e-9))
nc=c/(e*np.linalg.norm(x))
order=np.argsort(nc)[::-1]
k=int(order[0]); print(f"coarse: {k/SR:.3f}s corr={nc[k]:.3f}; runner-up far away:", end=" ")
for j in order:
    if abs(j-k)>SR*2: print(f"{j/SR:.3f}s corr={nc[j]:.3f}"); break
# fine at 48k
SR2=48000; t0=max(k/SR-1,0)
r=load(src,SR2,ss=t0,t=L/SR+2); y=load(clip,SR2)
c2,N2=xc(r,y); k2=int(np.argmax(c2[:len(r)]))
pk=c2[k2]/(np.linalg.norm(r[k2:k2+len(y)])*np.linalg.norm(y))
start=t0+k2/SR2
print(f"fine: clip starts at source {start:.5f}s = sample {round(start*SR2)}  corr={pk:.4f}  len={len(y)/SR2:.3f}s")
seg=r[k2:k2+len(y)]; g=np.dot(seg,y)/np.dot(seg,seg); print(f"gain clip/source = {20*np.log10(abs(g)):+.2f} dB (sign {np.sign(g):+.0f})")
