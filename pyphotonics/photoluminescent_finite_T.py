
import numpy as np
from numpy import fft
from pyphotonics.xyz import XYZ
import sys
import matplotlib.pyplot as plt
import cmath
from pyphotonics.configuration_coordinate import ConfigurationCoordinate
from scipy import constants

class Photoluminescence:

    def vasp_read_modes(self):
        return 0

    '''
    Read the vibrational modes that are calculated by phonopy
    '''
    def phonopy_read_modes(self):
        modes = np.zeros((self.numModes, self.numAtoms, 3))

        try:
            band = open(self.path + "band.yaml", 'r')
        except OSError:
            print("Could not open/read file: band.yaml")
            sys.exit()

        for line in band:
            if "  band:" in line:
                break

        for i in range(self.numModes):
            band.readline()
            band.readline()
            band.readline()

            for a in range(self.numAtoms):
                line = band.readline()

                line = band.readline().replace(",", "")

                parts = line.strip().split()
                modes[i][a][0] = float(parts[2])

                line = band.readline().replace(",", "")
                parts = line.strip().split()
                modes[i][a][1] = float(parts[2])

                line = band.readline().replace(",", "")
                parts = line.strip().split()
                modes[i][a][2] = float(parts[2])

        band.close()

        return modes

    '''
    Read the vibrational frequencies that are calculated by phonopy
    from the band.yaml file.
    '''
    def phonopy_read_frequencies(self):
        frequencies = np.zeros(self.numModes)
        try:
            band = open(self.path + "band.yaml", 'r')
        except OSError:
            print("Could not open/read file: band.yaml")
            sys.exit()

        for line in band:
            if "  band:" in line:
                break

        for i in range(self.numModes):
            band.readline()
            line = band.readline()

            parts = line.strip().split()
            frequencies[i] = float(parts[1])

            line = band.readline()

            for a in range(self.numAtoms):
                band.readline()
                band.readline()
                band.readline()
                band.readline()

        band.close()
        return frequencies

    def vasp_read_frequencies(self):
        return 0

    def get_S_omega(self, omega, sigma):
        sum = 0
        for k in range(len(self.S)):
            sum += self.S[k] * self.gaussian(omega, self.frequencies[k], sigma)
        return sum

    def get_C_omega_T(self, omega, sigma):
        sum = 0
        for k in range(len(self.C_t_T)):
            sum += self.C_t_T[k] * self.gaussian(omega, self.frequencies[k], sigma)
        return sum

    def gaussian(self, omega, omega_k, sigma):
        return 1 / (np.sqrt(2 * np.pi) * sigma) * np.exp(-(omega - omega_k) * (omega - omega_k) / sigma / sigma / 2)

    def write_S(self, file_name):
        f = open(file_name, 'w')
        for i in range(len(self.S_omega)):
            # f.write(str(self.omega_set[i]) + "\t" + str(self.S_omega[i])+'\n')
            f.write(str(self.S_omega[i])+'\n')
        f.close()

    '''
    The actual photoluminescence line-shape calculation:
    Calculate the line-shape function after reading the calculated vibrational data
    '''
    def PL(self, gamma, SHR, EZPL):
        Gt = [] #The Fourier-tranformed G function
        I = [] #The PL intensity function

        r = 1/self.resolution
        St = fft.ifft(self.S_omega)
        St = fft.ifftshift(St) #The Fourier-transformed partial HR function
        Ct_T = fft.ifft(self.C_omega_T)
        Ct_T = fft.ifftshift(Ct_T)
        Ct_T.imag = 0.0 # C_t_T + C_-t_T = 2(Real(C_t_T)j)
        Coeff = 2*np.pi*(St + 2*Ct_T) - self.HuangRhyes - 2*self.C_0_T  
        #G = np.exp(2*np.pi*St -SHR)
        G = np.exp(Coeff)

        for i in range(len(G)):
            t = r*(i-len(G)/2)
            Gt += [G[i]*np.exp(-gamma*np.abs(t))]

        A = fft.fft(Gt)

        # Now, shift the ZPL peak to the EZPL energy value
        tA = A.copy()
        for i in range(len(A)):
            A[(int(EZPL*self.resolution)-i) % len(A)] = tA[i]

        for i in range(len(A)):
            I += [A[i]*((i)*r)**3]

        return A, np.array(I)

    def __init__(self, path, str_g, str_e, numModes, method, m, resolution, shift_vector=[], temp=0.0):
        self.resolution = resolution
        self.numModes = numModes
        self.path = path
        self.m = m

        if '.xyz' in str_g:
            self.g = XYZ(str_g).coordinates
            self.e = XYZ(str_e).coordinates
        else:
            cc = ConfigurationCoordinate()
            self.g = cc.read_poscar(str_g)
            self.e = cc.read_poscar(str_e)

            self.g.translate_sites(
                range(len(self.g.frac_coords)), shift_vector, frac_coords=False)
            self.e.translate_sites(
                range(len(self.e.frac_coords)), shift_vector, frac_coords=False)

            lg = self.g.lattice
            le = self.e.lattice
            self.g = lg.get_cartesian_coords(self.g.frac_coords)
            self.e = le.get_cartesian_coords(self.e.frac_coords)

        self.numAtoms = len(self.g)
        self.method = method
        self.m = m

        if "phonopy" in method:
            r = self.phonopy_read_modes()
            self.frequencies = self.phonopy_read_frequencies()
        else:
            r = self.vasp_read_modes()
            self.frequencies = self.vasp_read_frequencies()

        self.C_0_T = 0
        self.HuangRhyes = 0
        self.Delta_R = 0
        self.Delta_Q = 0
        self.IPR = []
        self.q = []
        self.S = []
        self.C_t_T = []

        for i in range(numModes):
            q_i = 0
            IPR_i = 0
            participation = 0
            if method == "vasp":
                self.frequencies[i] = self.frequencies[i] / 1000
            elif method == "phonopy":
                self.frequencies[i] = self.frequencies[i] * \
                    0.004135665538536  # THz
            elif method == "phonopy-siesta":
                self.frequencies[i] = self.frequencies[i] * \
                    0.004135665538536 * 0.727445665  # THz

            if self.frequencies[i] < 0:
                self.frequencies[i] = 0

            max_Delta_r = 0

            D_R = self.e - self.g

            for a in range(self.numAtoms):
                # Normalize r:
                participation = r[i][a][0] * r[i][a][0] + \
                    r[i][a][1] * r[i][a][1] + r[i][a][2] * r[i][a][2]
                IPR_i += participation**2

                for coord in range(3):
                    q_i += np.sqrt(m[a]) * (D_R[a][coord]) * \
                        r[i][a][coord] * 1e-10
                    if np.abs(r[i][a][coord]) > max_Delta_r:
                        max_Delta_r = np.abs(r[i][a][coord])

            IPR_i = 1.0 / IPR_i
            S_i = self.frequencies[i] * q_i**2 / 2 * 1.0 / \
                (1.0545718e-34 * 6.582119514e-16)

            #hbar = (1.0545718e-34 * 6.582119514e-16)
            #self.frequencies[i] is already in eV unit
            #1 kelvin = 0.00008617328149741 electron-volt
            if temp > 0.0:
                number_occ_phonon_i = 1.0/(np.exp((self.frequencies[i])/\
                    (0.00008617328149741 * temp)) - 1.0)
            else:
                number_occ_phonon_i = 0.0
            C_i =  number_occ_phonon_i*S_i   
            self.C_t_T += [C_i]
            self.C_0_T += C_i


            self.IPR += [IPR_i]
            self.q += [q_i]
            self.S += [S_i]
            self.HuangRhyes += S_i

        for a in range(self.numAtoms):
            for coord in range(3):
                self.Delta_R += (D_R[a][coord])**2
                self.Delta_Q += (D_R[a][coord])**2 * m[a]

        self.Delta_R = self.Delta_R**0.5

        self.Delta_Q = (self.Delta_Q / 1.660539040e-27) ** 0.5

        self.max_energy = 5

        self.omega_set = np.linspace(
            0, self.max_energy, self.max_energy*self.resolution)
        self.S_omega = [self.get_S_omega(o, 6e-3) for o in self.omega_set]
        self.C_omega_T = [self.get_C_omega_T(o, 6e-3) for o in self.omega_set]
        


    def print_table(self):
        for i in range(self.numModes):
            print("IPR\t", i, "\tSk\t", self.S[i], "\tenergy\t",
                  self.frequencies[i], "\t=\t", self.IPR[i], "\twith localization ratio beta =\t", 64 / self.IPR[i])
