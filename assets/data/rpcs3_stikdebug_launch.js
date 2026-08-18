// NeoStation RPCS3 direct title launcher (second StikDebug pass).
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js
//
// Pass one has already enabled JIT and the user has pressed RPCS3's native
// Start button. This script attaches to the running process, fingerprints the
// loaded RPCS3 core, chooses the matching exported boot-function offset, calls
// rpcs3_ios_boot_game(title_id), restores registers and detaches. Unknown cores
// fail closed instead of jumping to an unverified address.

const neoTitleId = __NEOSTATION_TITLE_ID_JSON__;
const neoSupportedCoreOffsets = __NEOSTATION_SUPPORTED_CORES_JSON__;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

let pid = get_pid();
let attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`NEOSTATION_RPC_DIRECT_PID: ${pid}`);
log(`NEOSTATION_RPC_DIRECT_ATTACH: ${attachResponse}`);

try {
    const tid = resolveStoppedThread(attachResponse);
    if (!tid) throw new Error('Could not determine a stopped RPCS3 thread');

    const fingerprint = findFingerprintCore();
    if (!fingerprint) {
        log('NEOSTATION_RPC_DIRECT_CORE_NOT_READY');
        throw new Error('libRPCS3Core.dylib is not loaded yet');
    }

    callBootGame(fingerprint.core, fingerprint.bootOffset, tid);
    log(`NEOSTATION_RPC_DIRECT_BOOT_COMPLETED: ${neoTitleId}`);
} catch (error) {
    log(`NEOSTATION_RPC_DIRECT_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DIRECT_DETACH: ${detachResponse}`);
}

function resolveStoppedThread(initialPacket) {
    let packet = initialPacket || '';
    let match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups['tid'];

    packet = send_command('?') || '';
    log(`NEOSTATION_RPC_DIRECT_STOP_PACKET: ${packet}`);
    match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups['tid'];

    const current = send_command('qC') || '';
    log(`NEOSTATION_RPC_DIRECT_CURRENT_THREAD: ${current}`);
    match = /^QC(?<tid>[0-9a-f]+)$/i.exec(current);
    return match ? match.groups['tid'] : null;
}

function findFingerprintCore() {
    const command = 'jGetLoadedDynamicLibrariesInfos:{"fetch_all_solibs":true,"information-level":"address-name-uuid"}';
    const raw = send_command(command);
    const jsonStart = raw ? raw.indexOf('{') : -1;
    if (jsonStart < 0) throw new Error(`No loaded-image JSON: ${raw}`);

    const payload = JSON.parse(raw.substring(jsonStart));
    const images = Array.isArray(payload.images) ? payload.images : [];
    const core = images.find((image) =>
        String(image.pathname || '').includes('libRPCS3Core.dylib'));
    if (!core) return null;

    const actualUuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const rawOffset = neoSupportedCoreOffsets[actualUuid];
    if (rawOffset === undefined || rawOffset === null) {
        throw new Error(
            `Unsupported RPCS3 core UUID: ${actualUuid}; supported=${Object.keys(neoSupportedCoreOffsets).join(',')}`);
    }

    const bootOffset = BigInt(rawOffset);
    log(`NEOSTATION_RPC_DIRECT_FINGERPRINT: uuid=${actualUuid} offset=0x${bootOffset.toString(16)}`);
    return { core: core, bootOffset: bootOffset };
}

function callBootGame(core, bootOffset, tid) {
    const loadAddress = parseRemoteAddress(core.load_address);
    const bootAddress = loadAddress + bootOffset;
    log(`NEOSTATION_RPC_DIRECT_CORE: load=0x${loadAddress.toString(16)} boot=0x${bootAddress.toString(16)}`);

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
    const prepared = prepare_memory_region(scratch, 0x4000n);
    log(`NEOSTATION_RPC_DIRECT_SCRATCH: 0x${scratch.toString(16)} prepare=${prepared}`);

    try {
        const titleHex = asciiToHex(neoTitleId + '\0');
        const titleWrite = send_command(
            `M${scratch.toString(16)},${(titleHex.length / 2).toString(16)}:${titleHex}`);
        if (titleWrite !== 'OK') throw new Error(`Could not write title ID: ${titleWrite}`);

        const trap = scratch + 0x100n;
        const trapWrite = send_command(
            `M${trap.toString(16)},4:${neoReturnTrapInstruction}`);
        if (trapWrite !== 'OK') throw new Error(`Could not write return trap: ${trapWrite}`);

        const x0Write = send_command(
            `P0=${numberToLittleEndianHexString(scratch)};thread:${tid};`);
        const lrWrite = send_command(
            `P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
        const pcWrite = send_command(
            `P20=${numberToLittleEndianHexString(bootAddress)};thread:${tid};`);
        if (x0Write !== 'OK' || lrWrite !== 'OK' || pcWrite !== 'OK') {
            throw new Error(`Register write failed: x0=${x0Write} lr=${lrWrite} pc=${pcWrite}`);
        }

        const stop = send_command(`vCont;c:${tid}`);
        log(`NEOSTATION_RPC_DIRECT_BOOT_RETURN: ${stop}`);
        const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
        log(`NEOSTATION_RPC_DIRECT_RESTORE: ${restore}`);
        if (restore !== 'OK') throw new Error(`Could not restore registers: ${restore}`);
    } finally {
        send_command(`_m${scratch.toString(16)}`);
    }
}

function parseRemoteAddress(value) {
    if (typeof value === 'number') return BigInt(Math.trunc(value));
    const text = String(value || '').trim();
    if (!text) throw new Error('Missing remote load address');
    return BigInt(text);
}

function asciiToHex(text) {
    let result = '';
    for (let index = 0; index < text.length; index++) {
        result += text.charCodeAt(index).toString(16).padStart(2, '0');
    }
    return result;
}

function numberToLittleEndianHexString(number) {
    const bytes = [];
    let value = number;
    for (let index = 0; index < 8; index++) {
        bytes.push(Number(value & 0xffn));
        value >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
