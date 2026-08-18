// NeoStation RPCS3 state-aware direct title launcher.
// Derived from StikDebug Universal JIT Script (GPL-3.0):
// https://github.com/StikDebug/StikDebug/blob/main/StikDebug/Scripts/universal.js

const neoRequest = __NEOSTATION_REQUEST_JSON__;
const neoSupportedCores = __NEOSTATION_SUPPORTED_CORES_JSON__;
const neoReturnTrapInstruction = 'c0013ed4'; // brk #0xf00e, little endian

const pid = get_pid();
const attachResponse = send_command(`vAttach;${pid.toString(16)}`);
log(`NEOSTATION_RPC_REQUEST: ${JSON.stringify(neoRequest)}`);
log(`NEOSTATION_RPC_PROCESS: pid=${pid} attach=${attachResponse}`);

let scratch = 0n;
try {
    const tid = resolveStoppedThread(attachResponse);
    if (!tid) throw new Error('Could not determine a stopped RPCS3 thread');
    log(`NEOSTATION_RPC_THREAD: ${tid}`);

    const fingerprint = findFingerprintCore();
    if (!fingerprint) throw new Error('libRPCS3Core.dylib is not loaded');
    const core = fingerprint.core;
    const functions = fingerprint.functions;
    const base = parseRemoteAddress(core.load_address);
    log(`NEOSTATION_RPC_CORE_UUID: ${fingerprint.uuid}`);
    log(`NEOSTATION_RPC_MODULE_BASE: 0x${base.toString(16)}`);

    scratch = allocateScratch();
    const trap = scratch + 0x100n;
    writeMemory(trap, neoReturnTrapInstruction, 'return trap');

    const globalStateBefore = functions.globalState == null
        ? null
        : callUInt64(base + BigInt(functions.globalState), [], tid, trap, 'global-state-before');
    const emulationStateBefore = functions.emulationState == null
        ? null
        : callUInt64(base + BigInt(functions.emulationState), [], tid, trap, 'emulation-state-before');
    log(`NEOSTATION_RPC_STATE_BEFORE: global=${formatValue(globalStateBefore)} emulation=${formatValue(emulationStateBefore)}`);

    const progressBefore = functions.bootProgress == null
        ? null
        : callBootProgress(base + BigInt(functions.bootProgress), tid, trap);
    if (progressBefore != null) {
        log(`NEOSTATION_RPC_PROGRESS_BEFORE: ${JSON.stringify(progressBefore)}`);
    }

    // RPCS3 0.2's exported boot function requires the iOS core state to be 2.
    // This replaces the old timing guesses with the same state the function
    // itself checks internally.
    if (globalStateBefore != null && globalStateBefore !== 2n) {
        throw new Error(`RPCS3Core is not ready (global state ${globalStateBefore})`);
    }

    const titleAddress = scratch + 0x800n;
    const titleHex = asciiToHex(neoRequest.titleId + '\0');
    writeMemory(titleAddress, titleHex, 'title ID');
    log(`NEOSTATION_RPC_TITLE_POINTER: 0x${titleAddress.toString(16)} value=${neoRequest.titleId}`);

    const bootAddress = base + BigInt(functions.boot);
    log(`NEOSTATION_RPC_BOOT_ADDRESS: 0x${bootAddress.toString(16)}`);
    const bootResult = callUInt64(
        bootAddress,
        [titleAddress],
        tid,
        trap,
        'boot-game');
    log(`NEOSTATION_RPC_BOOT_RESULT: ${bootResult} (${bootResultName(bootResult)})`);

    let lastError = '';
    if (functions.lastError != null) {
        const errorPointer = callUInt64(
            base + BigInt(functions.lastError),
            [],
            tid,
            trap,
            'last-error');
        if (errorPointer != 0n) {
            lastError = readCString(errorPointer, 768);
        }
    }
    log(`NEOSTATION_RPC_LAST_ERROR: ${lastError || '<empty>'}`);

    const globalStateAfter = functions.globalState == null
        ? null
        : callUInt64(base + BigInt(functions.globalState), [], tid, trap, 'global-state-after');
    const emulationStateAfter = functions.emulationState == null
        ? null
        : callUInt64(base + BigInt(functions.emulationState), [], tid, trap, 'emulation-state-after');
    log(`NEOSTATION_RPC_STATE_AFTER: global=${formatValue(globalStateAfter)} emulation=${formatValue(emulationStateAfter)}`);

    const progressAfter = functions.bootProgress == null
        ? null
        : callBootProgress(base + BigInt(functions.bootProgress), tid, trap);
    if (progressAfter != null) {
        log(`NEOSTATION_RPC_PROGRESS_AFTER: ${JSON.stringify(progressAfter)}`);
    }

    if (bootResult !== 0n) {
        throw new Error(`rpcs3_ios_boot_game returned ${bootResultName(bootResult)}${lastError ? `: ${lastError}` : ''}`);
    }
    log(`NEOSTATION_RPC_BOOT_CONFIRMED: ${neoRequest.titleId}`);
} catch (error) {
    log(`NEOSTATION_RPC_ERROR: ${error && error.stack ? error.stack : error}`);
} finally {
    if (scratch !== 0n) send_command(`_m${scratch.toString(16)}`);
    const detachResponse = send_command('D');
    log(`NEOSTATION_RPC_DETACH: ${detachResponse}`);
}

function resolveStoppedThread(initialPacket) {
    let packet = initialPacket || '';
    let match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    packet = send_command('?') || '';
    match = /thread:(?<tid>[0-9a-f]+);/i.exec(packet);
    if (match) return match.groups.tid;
    const current = send_command('qC') || '';
    match = /^QC(?<tid>[0-9a-f]+)$/i.exec(current);
    return match ? match.groups.tid : null;
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
    const uuid = String(core.uuid || '').replace(/-/g, '').toUpperCase();
    const functions = neoSupportedCores[uuid];
    if (functions == null) {
        throw new Error(`Unsupported RPCS3 core UUID: ${uuid}`);
    }
    return { core, uuid, functions };
}

function allocateScratch() {
    let response = send_command('_M4000,rwx');
    if (!response || response.startsWith('E')) response = send_command('_M4000,rw');
    if (!response || response.startsWith('E')) {
        throw new Error(`Could not allocate remote scratch memory: ${response}`);
    }
    const address = BigInt(`0x${response}`);
    const prepared = prepare_memory_region(address, 0x4000n);
    log(`NEOSTATION_RPC_SCRATCH: 0x${address.toString(16)} prepare=${prepared}`);
    return address;
}

function callUInt64(address, args, tid, trap, label) {
    const saveId = send_command(`QSaveRegisterState;thread:${tid};`);
    if (!saveId || !/^[0-9]+$/.test(saveId)) {
        throw new Error(`${label}: could not save registers: ${saveId}`);
    }
    try {
        for (let index = 0; index < 4; index++) {
            const value = index < args.length ? BigInt(args[index]) : 0n;
            const write = send_command(
                `P${index.toString(16)}=${numberToLittleEndianHexString(value)};thread:${tid};`);
            if (write !== 'OK') throw new Error(`${label}: x${index} write failed: ${write}`);
        }
        const lrWrite = send_command(`P1e=${numberToLittleEndianHexString(trap)};thread:${tid};`);
        const pcWrite = send_command(`P20=${numberToLittleEndianHexString(address)};thread:${tid};`);
        if (lrWrite !== 'OK' || pcWrite !== 'OK') {
            throw new Error(`${label}: lr=${lrWrite} pc=${pcWrite}`);
        }
        const stop = send_command(`vCont;c:${tid}`) || '';
        let result = extractRegister(stop, '00');
        if (result == null) {
            const raw = send_command(`p0;thread:${tid};`) || send_command('p0') || '';
            result = /^[0-9a-f]{16}$/i.test(raw) ? littleEndianHexStringToNumber(raw) : null;
        }
        if (result == null) throw new Error(`${label}: return register unavailable; stop=${stop}`);
        log(`NEOSTATION_RPC_CALL: ${label} address=0x${address.toString(16)} result=${result}`);
        return result;
    } finally {
        const restore = send_command(`QRestoreRegisterState:${saveId};thread:${tid};`);
        if (restore !== 'OK') log(`NEOSTATION_RPC_RESTORE_ERROR: ${label} ${restore}`);
    }
}

function callBootProgress(address, tid, trap) {
    const current = scratch + 0x200n;
    const total = scratch + 0x208n;
    const text = scratch + 0x300n;
    writeMemory(current, '00000000', 'progress current');
    writeMemory(total, '00000000', 'progress total');
    writeMemory(text, '00', 'progress text');
    const status = callUInt64(address, [current, total, text, 1024n], tid, trap, 'boot-progress');
    return {
        status: Number(status),
        current: readU32(current),
        total: readU32(total),
        text: readCString(text, 1024),
    };
}

function writeMemory(address, hex, label) {
    const response = send_command(`M${address.toString(16)},${(hex.length / 2).toString(16)}:${hex}`);
    if (response !== 'OK') throw new Error(`${label} write failed: ${response}`);
}

function readU32(address) {
    const raw = send_command(`m${address.toString(16)},4`) || '';
    if (!/^[0-9a-f]{8}$/i.test(raw)) return -1;
    return Number(littleEndianHexStringToNumber(raw));
}

function readCString(address, maxBytes) {
    const raw = send_command(`m${address.toString(16)},${maxBytes.toString(16)}`) || '';
    return hexToAscii(raw);
}

function extractRegister(packet, registerTag) {
    const expression = new RegExp(`${registerTag}:(?<reg>[0-9a-f]{16});`, 'i');
    const match = expression.exec(packet);
    return match ? littleEndianHexStringToNumber(match.groups.reg) : null;
}

function bootResultName(value) {
    const number = Number(value);
    switch (number) {
        case 0: return 'success';
        case 1: return 'invalid-title-id';
        case 2: return 'core-not-ready';
        case 10: return 'internal-boot-failure';
        case 14: return 'title-not-found';
        default: return `status-${number}`;
    }
}

function formatValue(value) {
    return value == null ? 'unavailable' : value.toString();
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

function hexToAscii(hex) {
    let result = '';
    for (let index = 0; index + 1 < hex.length; index += 2) {
        const value = parseInt(hex.substring(index, index + 2), 16);
        if (!Number.isFinite(value) || value === 0) break;
        result += String.fromCharCode(value);
    }
    return result;
}

function littleEndianHexStringToNumber(hex) {
    const bytes = [];
    for (let index = 0; index < hex.length; index += 2) {
        bytes.push(parseInt(hex.substring(index, index + 2), 16));
    }
    let result = 0n;
    for (let index = bytes.length - 1; index >= 0; index--) {
        result = (result << 8n) | BigInt(bytes[index]);
    }
    return result;
}

function numberToLittleEndianHexString(number) {
    const bytes = [];
    let value = BigInt(number);
    for (let index = 0; index < 8; index++) {
        bytes.push(Number(value & 0xffn));
        value >>= 8n;
    }
    return bytes.map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
