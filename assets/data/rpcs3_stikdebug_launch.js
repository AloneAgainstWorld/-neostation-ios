// NeoStation RPCS3 title launcher.
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js
// The RPCS3-specific boot call is guarded by the exact core UUID and symbol
// offset observed in RPCS3 iOS 0.1 (1). A mismatch detaches without calling it.

const CMD_DETACH = 0;
const CMD_PREPARE_REGION = 1;
const CMD_NEW_BREAKPOINTS = 2;
const commands = {
    [CMD_DETACH]: JIT26Detach,
    [CMD_PREPARE_REGION]: JIT26PrepareRegion,
    [CMD_NEW_BREAKPOINTS]: JIT26NewBreakpoints
};
const legacyCommands = {
    [0x68]: JIT26NewBreakpoints,
    [0x69]: JIT26HandleBrk0x69,
    [0xf00d]: JIT26HandleBrk0xf00d
};
const LOG_INFO = 1;
const LOG_VERBOSE = 2;
let logLevel = LOG_VERBOSE;
function log_verbose(msg) { if (logLevel >= LOG_VERBOSE) log(msg); }

const neoTitleId = __NEOSTATION_TITLE_ID_JSON__;
const neoExpectedCoreUuid = __NEOSTATION_CORE_UUID_JSON__;
const neoBootGameOffset = 0x__NEOSTATION_BOOT_OFFSET_HEX__n;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

let tid, x0, x1, x16, pc;
let detached = false;
let continuesWithSignal = true;
let pid = get_pid();
let attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`pid = ${pid}`);
log(`attach_response = ${attachResponse}`);

let totalBreakpoints = 0;
while (!detached) {
    totalBreakpoints++;
    log(`Handling signal ${totalBreakpoints}`);
    let brkResponse = send_command(`c`);
    log_verbose(`brkResponse = ${brkResponse}`);

    let tmpMatch = /T[0-9a-f]+thread:(?<tid>[0-9a-f]+);/.exec(brkResponse);
    tid = tmpMatch ? tmpMatch.groups['tid'] : null;
    tmpMatch = /20:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    pc = tmpMatch ? tmpMatch.groups['reg'] : null;
    tmpMatch = /10:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
    x16 = tmpMatch ? tmpMatch.groups['reg'] : null;
    if (!tid || !pc || !x16) {
        log(`Failed to extract registers: tid=${tid}, pc=${pc}, x16=${x16}`);
        continue;
    }
    pc = littleEndianHexStringToNumber(pc);
    x16 = littleEndianHexStringToNumber(x16);

    let instructionResponse = send_command(`m${pc.toString(16)},4`);
    let instrU32 = littleEndianHexToU32(instructionResponse);
    if ((instrU32 & 0xFFE0001F) >>> 0 != 0xD4200000) {
        if (continuesWithSignal) {
            let signum = /^T(?<sig>[a-z0-9;]{2})/.exec(brkResponse);
            signum = signum ? signum.groups['sig'] : null;
            if (signum) send_command(`vCont;S${signum}:${tid}`);
        }
        continue;
    }

    let brkImmediate = extractBrkImmediate(instrU32);
    if (legacyCommands[brkImmediate] != undefined) {
        tmpMatch = /00:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
        x0 = tmpMatch ? tmpMatch.groups['reg'] : null;
        tmpMatch = /01:(?<reg>[0-9a-f]{16});/.exec(brkResponse);
        x1 = tmpMatch ? tmpMatch.groups['reg'] : null;
        if (!x0 || !x1) continue;
        x0 = littleEndianHexStringToNumber(x0);
        x1 = littleEndianHexStringToNumber(x1);

        let pcPlus4 = numberToLittleEndianHexString(pc + 4n);
        send_command(`P20=${pcPlus4};thread:${tid};`);
        legacyCommands[brkImmediate](brkResponse);
    }
}

function JIT26Detach() {
    try {
        neoStationBootRpcs3Title();
    } catch (error) {
        log(`NEOSTATION_RPC_BOOT_ERROR: ${error && error.stack ? error.stack : error}`);
    }
    let detachResponse = send_command(`D`);
    log(`NEOSTATION_RPC_DETACH: ${detachResponse}`);
    detached = true;
}

function neoStationBootRpcs3Title() {
    log(`NEOSTATION_RPC_BOOT_REQUEST: ${neoTitleId}`);
    const libraryCommand = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const rawLibraries = send_command(libraryCommand);
    const jsonStart = rawLibraries ? rawLibraries.indexOf('{') : -1;
    if (jsonStart < 0) throw new Error(`No loaded-image JSON: ${rawLibraries}`);
    const payload = JSON.parse(rawLibraries.substring(jsonStart));
    const images = Array.isArray(payload.images) ? payload.images : [];
    const core = images.find((image) => String(image.pathname || '').includes('libRPCS3Core.dylib'));
    if (!core) throw new Error('libRPCS3Core.dylib is not loaded');

    const actualUuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const expectedUuid = neoExpectedCoreUuid.replace(/-/g, '').toUpperCase();
    if (actualUuid !== expectedUuid) {
        throw new Error(`RPCS3 core UUID mismatch: ${actualUuid} != ${expectedUuid}`);
    }

    const loadAddress = parseRemoteAddress(core.load_address);
    const bootAddress = loadAddress + neoBootGameOffset;
    log(`NEOSTATION_RPC_CORE: load=0x${loadAddress.toString(16)} boot=0x${bootAddress.toString(16)}`);

    const saveId = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saveId || !/^[0-9]+$/.test(saveId)) {
        throw new Error(`Could not save registers: ${saveId}`);
    }

    let scratchResponse = send_command('_M4000,rwx');
    if (!scratchResponse || scratchResponse.startsWith('E')) {
        scratchResponse = send_command('_M4000,rw');
    }
    if (!scratchResponse || scratchResponse.startsWith('E')) {
        throw new Error(`Could not allocate remote scratch memory: ${scratchResponse}`);
    }
    const scratch = BigInt(`0x${scratchResponse}`);
    const prep = prepare_memory_region(scratch, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${scratch.toString(16)} prepare=${prep}`);

    const titleHex = asciiToHex(neoTitleId + '\0');
    const titleWrite = send_command(`M${scratch.toString(16)},${(titleHex.length / 2).toString(16)}:${titleHex}`);
    if (titleWrite !== 'OK') throw new Error(`Could not write title ID: ${titleWrite}`);

    const trap = scratch + 0x100n;
    const trapWrite = send_command(`M${trap.toString(16)},4:${neoReturnTrapInstruction}`);
    if (trapWrite !== 'OK') throw new Error(`Could not write return trap: ${trapWrite}`);

    const x0Write = send_command(`P0=${numberToLittleEndianHexString(scratch)};thread:${tid};`);
    const lrWrite = send_command(`P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
    const pcWrite = send_command(`P20=${numberToLittleEndianHexString(bootAddress)};thread:${tid};`);
    if (x0Write !== 'OK' || lrWrite !== 'OK' || pcWrite !== 'OK') {
        throw new Error(`Register write failed: x0=${x0Write} lr=${lrWrite} pc=${pcWrite}`);
    }

    const callStop = send_command(`vCont;c:${tid}`);
    log(`NEOSTATION_RPC_BOOT_RETURN: ${callStop}`);
    const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
    log(`NEOSTATION_RPC_RESTORE: ${restore}`);
    send_command(`_m${scratch.toString(16)}`);
    if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
}

function JIT26NewBreakpoints(brkResponse) {
    let memResponse = send_command(`m${x0.toString(16)},${x1}`);
    let scriptText = hexToAscii(memResponse);
    try { eval(scriptText); } catch (err) { log(`Dynamic script failed: ${err}`); }
}

function JIT26HandleBrk0x69(brkResponse) {
    send_command(`P0=E0000069;thread:${tid};`);
}

function JIT26HandleBrk0xf00d(brkResponse) {
    const command = commands[x16];
    if (command !== undefined) command(brkResponse);
}

function JIT26PrepareRegion(brkResponse) {
    if (x0 == 0n && x1 == 0n) return;
    let jitPageAddress = x0;
    if (x0 == 0n) {
        const requestRXResponse = send_command(`_M${x1.toString(16)},rx`);
        if (!requestRXResponse) return;
        jitPageAddress = BigInt(`0x${requestRXResponse}`);
    }
    prepare_memory_region(jitPageAddress, x1);
    send_command(`P0=${numberToLittleEndianHexString(jitPageAddress)};thread:${tid};`);
}

function parseRemoteAddress(value) {
    if (typeof value === 'number') return BigInt(Math.trunc(value));
    const text = String(value || '').trim();
    if (!text) throw new Error('Missing remote load address');
    return text.startsWith('0x') || text.startsWith('0X') ? BigInt(text) : BigInt(text);
}

function asciiToHex(text) {
    let result = '';
    for (let i = 0; i < text.length; i++) {
        result += text.charCodeAt(i).toString(16).padStart(2, '0');
    }
    return result;
}

function littleEndianHexStringToNumber(hexStr) {
    const bytes = [];
    for (let i = 0; i < hexStr.length; i += 2) bytes.push(parseInt(hexStr.substr(i, 2), 16));
    let num = 0n;
    for (let i = Math.min(bytes.length, 8) - 1; i >= 0; i--) num = (num << 8n) | BigInt(bytes[i]);
    return num;
}

function numberToLittleEndianHexString(num) {
    const bytes = [];
    for (let i = 0; i < 8; i++) {
        bytes.push(Number(num & 0xFFn));
        num >>= 8n;
    }
    return bytes.map((b) => b.toString(16).padStart(2, '0')).join('');
}

function littleEndianHexToU32(hexStr) {
    return parseInt(hexStr.match(/../g).reverse().join(''), 16);
}

function extractBrkImmediate(u32) { return (u32 >> 5) & 0xFFFF; }

function hexToAscii(hexStr) {
    let str = '';
    for (let i = 0; i < hexStr.length; i += 2) {
        const byte = parseInt(hexStr.substr(i, 2), 16);
        if (byte === 0) break;
        str += String.fromCharCode(byte);
    }
    return str;
}
