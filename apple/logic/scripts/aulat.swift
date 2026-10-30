// aulat.swift: measure the real latency of AU plugin instances from their ClassInfo plists.
// usage (macOS, in the logged-in GUI session, not plain ssh):
//   swiftc -O aulat.swift -o aulat && ./aulat <dir of NNN_<offset>.plist files> > lat.txt
// Each line: <file> <subtype> <manufacturer> ch=.. ci=.. init=.. latErr=.. samples=<n at 48 kHz> ms=..
import AudioToolbox
import Foundation
var out:[String]=[]
let dir=CommandLine.arguments[1]
let files=try! FileManager.default.contentsOfDirectory(atPath:dir).filter{$0.hasSuffix(".plist")}.sorted()
func fcc(_ v:UInt32)->String{ let b=[UInt8((v>>24)&255),UInt8((v>>16)&255),UInt8((v>>8)&255),UInt8(v&255)]; return String(bytes:b,encoding:.ascii) ?? "?" }
for f in files {
  let url=URL(fileURLWithPath:dir+"/"+f)
  guard let dict=NSDictionary(contentsOf:url) else { print(f,"noplist"); continue }
  var desc=AudioComponentDescription(componentType:(dict["type"] as! NSNumber).uint32Value, componentSubType:(dict["subtype"] as! NSNumber).uint32Value, componentManufacturer:(dict["manufacturer"] as! NSNumber).uint32Value, componentFlags:0, componentFlagsMask:0)
  let tag="\(f) \(fcc(desc.componentSubType)) \(fcc(desc.componentManufacturer))"
  guard let comp=AudioComponentFindNext(nil,&desc) else { print(tag,"NOTFOUND"); fflush(stdout); continue }
  var au:AudioUnit?
  if AudioComponentInstanceNew(comp,&au) != noErr || au==nil { print(tag,"NEWFAIL"); fflush(stdout); continue }
  var ch:UInt32 = 2
  for c:UInt32 in [1,2] {
    var asbd=AudioStreamBasicDescription(mSampleRate:48000,mFormatID:kAudioFormatLinearPCM,mFormatFlags:kAudioFormatFlagsNativeFloatPacked|kAudioFormatFlagIsNonInterleaved,mBytesPerPacket:4,mFramesPerPacket:1,mBytesPerFrame:4,mChannelsPerFrame:c,mBitsPerChannel:32,mReserved:0)
    let a=AudioUnitSetProperty(au!,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,0,&asbd,UInt32(MemoryLayout<AudioStreamBasicDescription>.size))
    let b=AudioUnitSetProperty(au!,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Output,0,&asbd,UInt32(MemoryLayout<AudioStreamBasicDescription>.size))
    if a==noErr && b==noErr { ch=c; break }
  }
  var mf:UInt32=1024; AudioUnitSetProperty(au!,kAudioUnitProperty_MaximumFramesPerSlice,kAudioUnitScope_Global,0,&mf,4)
  var pl:CFPropertyList = dict as CFPropertyList
  let ci=AudioUnitSetProperty(au!,kAudioUnitProperty_ClassInfo,kAudioUnitScope_Global,0,&pl,UInt32(MemoryLayout<CFPropertyList>.size))
  let ini=AudioUnitInitialize(au!)
  // a second ClassInfo set after init, some plugins only apply state when initialized
  var pl2:CFPropertyList = dict as CFPropertyList
  let ci2=AudioUnitSetProperty(au!,kAudioUnitProperty_ClassInfo,kAudioUnitScope_Global,0,&pl2,UInt32(MemoryLayout<CFPropertyList>.size))
  usleep(300000)
  var lat:Float64=0; var sz=UInt32(8)
  let lr=AudioUnitGetProperty(au!,kAudioUnitProperty_Latency,kAudioUnitScope_Global,0,&lat,&sz)
  print(tag,"ch=\(ch) ci=\(ci)/\(ci2) init=\(ini) latErr=\(lr) samples=\(Int((lat*48000).rounded())) ms=\(String(format:"%.2f",lat*1000))"); fflush(stdout)
  AudioUnitUninitialize(au!); AudioComponentInstanceDispose(au!)
}
